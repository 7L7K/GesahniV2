"use client";

import { wsUrl } from "@/lib/api";

type WSName = "music" | "care";
type Closeable = { close: () => void } | null;

class WsHub {
  private sockets: Record<WSName, WebSocket | null> = { music: null, care: null };
  private timers: Record<WSName, ReturnType<typeof setTimeout> | null> = { music: null, care: null };
  private queues: Record<WSName, string[]> = { music: [], care: [] };
  private lastPong: Record<WSName, number> = { music: 0, care: 0 };
  private startRefs: Record<WSName, number> = { music: 0, care: 0 };
  private config: Record<WSName, { path: string; onOpen: (ws: WebSocket) => void; onMessage: (e: MessageEvent) => void }> = {
    music: { path: "/v1/ws/music", onOpen: this.onMusicOpen, onMessage: this.onMusicMessage },
    care: { path: "/v1/ws/care", onOpen: this.onCareOpen, onMessage: this.onCareMessage },
  } as const;

  constructor() {
    // Resume aggressively when app becomes visible or network returns
    if (typeof window !== "undefined") {
      try {
        document.addEventListener("visibilitychange", () => {
          if (document.visibilityState === "visible") {
            this.resumeAll("visibility");
          }
        });
        window.addEventListener("focus", () => this.resumeAll("focus"));
        window.addEventListener("online", () => this.resumeAll("online"));
        // React immediately to auth token/epoch changes (switch namespaces)
        window.addEventListener("auth:tokens_set", () => this.refreshAuth());
        window.addEventListener("auth:tokens_cleared", () => this.refreshAuth());
        window.addEventListener("auth:epoch_bumped", () => this.refreshAuth());
      } catch {
        /* noop */
      }
    }
  }

  start(channels?: Partial<Record<WSName, boolean>>) {
    try { console.info('AUTH backend online=true'); } catch { }
    const want: Record<WSName, boolean> = {
      music: channels?.music !== false, // default to true for music
      care: Boolean(channels?.care),
    } as Record<WSName, boolean>;
    (Object.keys(want) as WSName[]).forEach((name) => {
      if (!want[name]) return;
      this.startRefs[name] += 1;
      if (this.startRefs[name] === 1) {
        if (name === "music") this.connect("music", "/v1/ws/music", this.onMusicOpen, this.onMusicMessage);
        if (name === "care") this.connect("care", "/v1/ws/care", this.onCareOpen, this.onCareMessage);
      }
    });
  }

  stop(channels?: Partial<Record<WSName, boolean>>) {
    try { console.info('AUTH backend online=false'); } catch { }
    const target: Record<WSName, boolean> = {
      music: channels?.music !== false, // default to true if unspecified
      care: channels?.care === true || channels?.care === undefined,
    } as Record<WSName, boolean>;
    (Object.keys(target) as WSName[]).forEach((name) => {
      if (!target[name]) return;
      if (this.startRefs[name] > 0) this.startRefs[name] -= 1;
      if (this.startRefs[name] === 0) {
        this.safeClose(this.sockets[name]);
        this.sockets[name] = null;
        if (this.timers[name]) {
          clearTimeout(this.timers[name]!);
          this.timers[name] = null;
        }
        this.queues[name] = [];
      }
    });
  }

  // ---------------- private helpers ----------------

  private safeClose(ws: Closeable) {
    try { ws && ws.close(); } catch { /* noop */ }
  }

  private jitteredDelayFor(retry: number) {
    const base = Math.min(30_000, 500 * Math.pow(2, retry)); // cap @ 30s
    const jitter = base * (0.15 * (Math.random() * 2 - 1));  // ±15%
    return Math.max(250, Math.floor(base + jitter));
  }

  private resumeAll(reason: string) {
    // Attempt immediate reconnects for any desired-but-not-open channels
    (Object.keys(this.startRefs) as WSName[]).forEach((name) => {
      if (this.startRefs[name] <= 0) return;
      const ws = this.sockets[name];
      const open = ws && ws.readyState === WebSocket.OPEN;
      const connecting = ws && ws.readyState === WebSocket.CONNECTING;
      if (open) {
        // Nudge alive
        try { ws!.send("ping"); } catch { /* noop */ }
        return;
      }
      if (connecting) return;
      // Clear any backoff timer and reconnect now
      if (this.timers[name]) { clearTimeout(this.timers[name]!); this.timers[name] = null; }
      const cfg = this.config[name];
      this.connect(name, cfg.path, cfg.onOpen, cfg.onMessage, 0);
    });
  }

  private refreshAuth() {
    // On auth changes, force-close and reconnect to propagate new token/namespace
    (Object.keys(this.startRefs) as WSName[]).forEach((name) => {
      if (this.startRefs[name] <= 0) return;
      this.safeClose(this.sockets[name]);
      this.sockets[name] = null;
      if (this.timers[name]) { clearTimeout(this.timers[name]!); this.timers[name] = null; }
      const cfg = this.config[name];
      this.connect(name, cfg.path, cfg.onOpen, cfg.onMessage, 0);
    });
  }

  private flushQueue(which: WSName) {
    const ws = this.sockets[which];
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const q = this.queues[which];
    while (q.length) {
      const payload = q.shift();
      if (payload == null) break;
      try { ws.send(payload); } catch { q.unshift(payload); break; }
    }
  }

  private async probeAuthAndMaybeRedirect() {
    // Do not hard-redirect on auth failures; surface an event for the UI to show CTA and pause.
    try {
      const { apiFetch } = await import("@/lib/api");
      const resp = await apiFetch("/v1/whoami", { method: "GET" });
      if (!resp.ok) {
        try { window.dispatchEvent(new CustomEvent("auth:required")); } catch { /* noop */ }
      }
    } catch {
      try { window.dispatchEvent(new CustomEvent("auth:required")); } catch { /* noop */ }
    }
  }

  // Generic connector with per-socket hooks
  private connect(
    name: WSName,
    path: string,
    onOpenExtra: (ws: WebSocket) => void,
    onMessage: (e: MessageEvent) => void,
    retry = 0
  ) {
    // Clean any previous socket
    this.safeClose(this.sockets[name]);

    try {
      const ws = new WebSocket(wsUrl(path), ["json.realtime.v1"]);
      this.sockets[name] = ws;

      // heartbeat: send ping every 25s
      const heartbeat = () => {
        try { ws.send('ping'); } catch { /* noop */ }
      };

      let hbTimer: ReturnType<typeof setInterval> | null = null;

      ws.onopen = () => {
        retry = 0; // reset backoff
        this.lastPong[name] = Date.now();
        try { onOpenExtra.call(this, ws); } catch { /* noop */ }
        this.flushQueue(name);
        if (hbTimer) clearInterval(hbTimer);
        hbTimer = setInterval(heartbeat, 25_000);
      };

      ws.onmessage = (e) => {
        try {
          const raw = String(e.data || "");
          // Handle pong responses first to avoid JSON.parse errors downstream
          if (raw === 'pong') { this.lastPong[name] = Date.now(); return; }
          onMessage.call(this, e);
        } catch { /* swallow to keep socket alive */ }
      };

      ws.onclose = () => {
        // Optional: probe auth on close to bounce to login if session expired
        this.probeAuthAndMaybeRedirect();
        if (hbTimer) { clearInterval(hbTimer); hbTimer = null; }
        const delay = this.jitteredDelayFor(retry++);
        this.timers[name] = setTimeout(() => this.connect(name, path, onOpenExtra, onMessage, retry), delay);
      };

      ws.onerror = () => {
        // Let onclose handle the reconnect; ensure socket is closed
        try { ws.close(); } catch { /* noop */ }
      };
    } catch {
      const delay = this.jitteredDelayFor(retry++);
      this.timers[name] = setTimeout(() => this.connect(name, path, onOpenExtra, onMessage, retry), delay);
    }
  }

  // ---------------- message handlers ----------------

  private onMusicOpen(ws: WebSocket) {
    // Send initial ping
    try { ws.send('ping'); } catch { /* noop */ }
  }

  private onMusicMessage(e: MessageEvent) {
    const raw = String(e.data ?? "");
    if (!raw || raw === 'pong') return;
    let msg: any;
    try { msg = JSON.parse(raw); } catch { return; }
    const topic = String(msg?.topic || "");
    if (topic === "music.state") {
      (window as any).__musicState = msg.data || {};
      // Broadcast with detail for consumers
      try { window.dispatchEvent(new CustomEvent("music.state", { detail: msg.data || {} })); } catch { /* noop */ }
      return;
    }
    // Fan-out any other music.* topics (e.g., music.queue.updated)
    if (topic.startsWith("music.")) {
      try { window.dispatchEvent(new CustomEvent(topic, { detail: msg.data ?? msg } as any)); } catch { /* noop */ }
    }
  }

  private onCareOpen(ws: WebSocket) {
    try {
      ws.send(JSON.stringify({ action: "subscribe", topic: "resident:me" }));
      // Send initial ping
      ws.send(JSON.stringify({ action: 'ping' }));
    } catch { /* noop */ }
  }

  private onCareMessage(e: MessageEvent) {
    const raw = String(e.data ?? "");
    if (!raw || raw === 'pong') return;
    let msg: any;
    try { msg = JSON.parse(raw); } catch { return; }
    const data = msg?.data || {};
    const event: string = String(data.event || "");

    if (event.startsWith("alert.")) {
      window.dispatchEvent(new CustomEvent("alert:incoming", { detail: data } as any));
    }

    if (event === "device.heartbeat") {
      (window as any).__deviceHeartbeatAt = Date.now();
      window.dispatchEvent(new CustomEvent("device.heartbeat"));
    }

    if (event === "tv.config.updated") {
      (window as any).__tvConfigLastUpdatedAt = Date.now();
      window.dispatchEvent(new CustomEvent("tv.config.updated", { detail: data } as any));
    }
  }

  // ---------------- public send APIs ----------------

  sendCare(data: unknown) {
    const payload = typeof data === "string" ? data : JSON.stringify(data ?? {});
    const ws = this.sockets.care;
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.send(payload); } catch { this.queues.care.push(payload); }
    } else {
      this.queues.care.push(payload);
    }
  }

  sendMusic(data: unknown) {
    const payload = typeof data === "string" ? data : JSON.stringify(data ?? {});
    const ws = this.sockets.music;
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.send(payload); } catch { this.queues.music.push(payload); }
    } else {
      this.queues.music.push(payload);
    }
  }
}

export const wsHub = new WsHub();
