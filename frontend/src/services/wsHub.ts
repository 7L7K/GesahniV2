"use client";

import { wsUrl } from "@/lib/api";

type WSName = "music" | "care";
type Closeable = { close: () => void } | null;

class WsHub {
  private sockets: Record<WSName, WebSocket | null> = { music: null, care: null };
  private timers: Record<WSName, ReturnType<typeof setTimeout> | null> = { music: null, care: null };
  private queues: Record<WSName, string[]> = { music: [], care: [] };
  private lastPong: Record<WSName, number> = { music: 0, care: 0 };

  start() {
    this.connect("music", "/v1/ws/music", this.onMusicOpen, this.onMusicMessage);
    this.connect("care", "/v1/ws/care", this.onCareOpen, this.onCareMessage);
  }

  stop() {
    (["music", "care"] as WSName[]).forEach((name) => {
      this.safeClose(this.sockets[name]);
      this.sockets[name] = null;
      if (this.timers[name]) {
        clearTimeout(this.timers[name]!);
        this.timers[name] = null;
      }
      this.queues[name] = [];
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
    try {
      const { apiFetch } = await import("@/lib/api");
      const resp = await apiFetch("/v1/whoami", { method: "GET" });
      if (!resp.ok) {
        try { window.location.assign("/login"); } catch { /* noop */ }
      }
    } catch {
      // Network flake — ignore and let reconnect logic handle it
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
      const ws = new WebSocket(wsUrl(path));
      this.sockets[name] = ws;

      ws.onopen = () => {
        retry = 0; // reset backoff
        this.lastPong[name] = Date.now();
        try { onOpenExtra.call(this, ws); } catch { /* noop */ }
        this.flushQueue(name);
      };

      ws.onmessage = (e) => {
        try {
          onMessage.call(this, e);
          // Handle pong responses
          if (String(e.data || "") === 'pong') {
            this.lastPong[name] = Date.now();
          }
        } catch { /* swallow to keep socket alive */ }
      };

      ws.onclose = () => {
        // Optional: probe auth on close to bounce to login if session expired
        this.probeAuthAndMaybeRedirect();
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
    const msg = JSON.parse(String(e.data ?? "{}"));
    if (msg && msg.topic === "music.state") {
      (window as any).__musicState = msg.data || {};
      window.dispatchEvent(new CustomEvent("music.state"));
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
    const msg = JSON.parse(String(e.data ?? "{}"));
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
