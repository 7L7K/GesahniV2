"use client";

import { wsUrl, apiFetch } from "@/lib/api";
import { getAuthOrchestrator } from '@/services/authOrchestrator';

type WSName = "music" | "care";
type Closeable = { close: () => void } | null;

interface ConnectionState {
  socket: WebSocket | null;
  timer: ReturnType<typeof setTimeout> | null;
  heartbeatTimer: ReturnType<typeof setInterval> | null; // Add heartbeat timer to connection state
  queue: string[];
  lastPong: number;
  startRefs: number;
  reconnectAttempts: number;
  maxReconnectAttempts: number;
  lastFailureTime: number;
  failureReason: string | null;
}

class WsHub {
  private connections: Record<WSName, ConnectionState> = {
    music: {
      socket: null,
      timer: null,
      heartbeatTimer: null,
      queue: [],
      lastPong: 0,
      startRefs: 0,
      reconnectAttempts: 0,
      maxReconnectAttempts: 20,
      lastFailureTime: 0,
      failureReason: null,
    },
    care: {
      socket: null,
      timer: null,
      heartbeatTimer: null,
      queue: [],
      lastPong: 0,
      startRefs: 0,
      reconnectAttempts: 0,
      maxReconnectAttempts: 20,
      lastFailureTime: 0,
      failureReason: null,
    },
  };

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
        // Also listen for general auth state changes to handle session_ready updates
        window.addEventListener("auth:state_changed", (event: CustomEvent) => {
          const detail = event.detail;
          // If session became ready, try to reconnect any failed connections
          if (!detail.prevState.session_ready && detail.newState.session_ready && detail.newState.is_authenticated) {
            console.info('WS Hub: Session became ready, attempting reconnection');
            this.resumeAll("session_ready");
          }
        });

        // Listen for backend status changes to trigger reconnection when backend comes online
        window.addEventListener("backend:status_changed", (event: CustomEvent) => {
          const detail = event.detail;
          if (detail.online) {
            console.info('WS Hub: Backend came online, attempting reconnection');
            this.resumeAll("backend_online");
          }
        });
      } catch (error) {
        console.warn('WS Hub: Failed to dispatch connection failure event', error);
      }
    }
  }

  start(channels?: Partial<Record<WSName, boolean>>) {
    try { console.info('AUTH backend online=true'); } catch (error) {
      console.warn('WS Hub: Failed to log backend online status', error);
    }
    const want: Record<WSName, boolean> = {
      music: channels?.music !== false, // default to true for music
      care: Boolean(channels?.care),
    } as Record<WSName, boolean>;
    (Object.keys(want) as WSName[]).forEach((name) => {
      if (!want[name]) return;
      this.connections[name].startRefs += 1;
      if (this.connections[name].startRefs === 1) {
        if (name === "music") this.connect("music", "/v1/ws/music", this.onMusicOpen, this.onMusicMessage);
        if (name === "care") this.connect("care", "/v1/ws/care", this.onCareOpen, this.onCareMessage);
      }
    });
  }

  stop(channels?: Partial<Record<WSName, boolean>>) {
    try { console.info('AUTH backend online=false'); } catch (error) {
      console.warn('WS Hub: Failed to log backend offline status', error);
    }
    const target: Record<WSName, boolean> = {
      music: channels?.music !== false, // default to true if unspecified
      care: channels?.care === true || channels?.care === undefined,
    } as Record<WSName, boolean>;
    (Object.keys(target) as WSName[]).forEach((name) => {
      if (!target[name]) return;
      if (this.connections[name].startRefs > 0) this.connections[name].startRefs -= 1;
      if (this.connections[name].startRefs === 0) {
        this.safeClose(this.connections[name].socket);
        this.connections[name].socket = null;
        if (this.connections[name].timer) {
          clearTimeout(this.connections[name].timer!);
          this.connections[name].timer = null;
        }
        if (this.connections[name].heartbeatTimer) {
          clearInterval(this.connections[name].heartbeatTimer!);
          this.connections[name].heartbeatTimer = null;
        }
        this.connections[name].queue = [];
        // Reset reconnection state when stopping
        this.connections[name].reconnectAttempts = 0;
        this.connections[name].failureReason = null;
      }
    });
  }

  // ---------------- public status APIs ----------------

  getConnectionStatus(name: WSName): { isOpen: boolean; isConnecting: boolean; failureReason: string | null; lastFailureTime: number } {
    const conn = this.connections[name];
    const ws = conn.socket;
    return {
      isOpen: Boolean(ws && ws.readyState === WebSocket.OPEN),
      isConnecting: Boolean(ws && ws.readyState === WebSocket.CONNECTING),
      failureReason: conn.failureReason,
      lastFailureTime: conn.lastFailureTime,
    };
  }

  // ---------------- private helpers ----------------

  private safeClose(ws: Closeable) {
    try { ws && ws.close(); } catch (error) {
      console.warn('WS Hub: Failed to close WebSocket', error);
    }
  }

  private jitteredDelayFor(retry: number) {
    // Backoff: 0.5s → 1s → 2s → 4s, cap at ~5s with light jitter
    const base = Math.min(5_000, 500 * Math.pow(2, retry));
    const jitter = base * (0.10 * (Math.random() * 2 - 1));  // ±10%
    return Math.max(500, Math.floor(base + jitter));
  }

  // Lightweight cached health gate to avoid WS attempts during outages
  private _healthCache: { ts: number; healthy: boolean } | null = null;
  private async isBackendHealthy(): Promise<boolean> {
    const now = Date.now();
    if (this._healthCache && (now - this._healthCache.ts) < 2000) {
      return this._healthCache.healthy;
    }
    try {
      // If whoami was recently green, allow reconnects regardless of health snapshot
      try {
        const authOrchestrator = getAuthOrchestrator();
        const s = authOrchestrator.getState();
        const last = Number(s.lastChecked || 0);
        const recent = last && (now - last) < 60_000; // 60s window
        if (s.is_authenticated && s.session_ready && recent) {
          this._healthCache = { ts: now, healthy: true };
          return true;
        }
      } catch (error) {
        console.debug('WS Hub: Failed to check recent auth state for health optimization', error);
      }
      const controller = new AbortController();
      const t = setTimeout(() => controller.abort(), 1500);
      const res = await apiFetch('/v1/health', { auth: true, dedupe: false, cache: 'no-store', signal: controller.signal });
      clearTimeout(t);
      // Treat 200 responses as online (even if degraded); only offline for network errors or 5xx
      let ok = false;
      if (res.status >= 500) {
        ok = false;
      } else if (res.ok) {
        ok = true;
      } else {
        ok = false;
      }
      this._healthCache = { ts: now, healthy: ok };
      return ok;
    } catch (error) {
      console.warn('WS Hub: Health check failed', error);
      this._healthCache = { ts: now, healthy: false };
      return false;
    }
  }

  private resumeAll(reason: string) {
    // Only attempt reconnects if authenticated
    const authOrchestrator = getAuthOrchestrator();
    const authState = authOrchestrator.getState();

    if (!(authState.is_authenticated && authState.session_ready)) {
      console.info('WS resumeAll: Skipping reconnects - not authenticated');
      return;
    }

    // Attempt immediate reconnects for any desired-but-not-open channels
    (Object.keys(this.connections) as WSName[]).forEach((name) => {
      if (this.connections[name].startRefs <= 0) return;
      const ws = this.connections[name].socket;
      const open = ws && ws.readyState === WebSocket.OPEN;
      const connecting = ws && ws.readyState === WebSocket.CONNECTING;
      if (open) {
        // Nudge alive
        try { ws!.send("ping"); } catch (error) {
          console.warn('WS Hub: Failed to send nudge ping in resumeAll', error);
        }
        return;
      }
      if (connecting) return;

      // Check if we've exceeded reconnection attempts
      if (this.connections[name].reconnectAttempts >= this.connections[name].maxReconnectAttempts) {
        console.warn(`WS ${name}: Max reconnection attempts reached, not attempting reconnect`);
        return;
      }

      // Clear any backoff timer and reconnect now
      if (this.connections[name].timer) {
        clearTimeout(this.connections[name].timer!);
        this.connections[name].timer = null;
      }
      const cfg = this.config[name];
      this.connect(name, cfg.path, cfg.onOpen, cfg.onMessage, 0);
    });
  }

  private refreshAuth() {
    // Only attempt reconnects if authenticated
    const authOrchestrator = getAuthOrchestrator();
    const authState = authOrchestrator.getState();

    if (!(authState.is_authenticated && authState.session_ready)) {
      console.info('WS refreshAuth: Skipping reconnects - not authenticated');
      return;
    }

    // On auth changes, force-close and reconnect to propagate new token/namespace
    (Object.keys(this.connections) as WSName[]).forEach((name) => {
      if (this.connections[name].startRefs <= 0) return;
      this.safeClose(this.connections[name].socket);
      this.connections[name].socket = null;
      if (this.connections[name].timer) {
        clearTimeout(this.connections[name].timer!);
        this.connections[name].timer = null;
      }
      if (this.connections[name].heartbeatTimer) {
        clearInterval(this.connections[name].heartbeatTimer!);
        this.connections[name].heartbeatTimer = null;
      }
      // Reset reconnection attempts on auth refresh
      this.connections[name].reconnectAttempts = 0;
      this.connections[name].failureReason = null;
      const cfg = this.config[name];
      this.connect(name, cfg.path, cfg.onOpen, cfg.onMessage, 0);
    });
  }

  private flushQueue(which: WSName) {
    const ws = this.connections[which].socket;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const q = this.connections[which].queue;
    let failedCount = 0;
    const maxRetries = 3;

    while (q.length && failedCount < maxRetries) {
      const payload = q.shift();
      if (payload == null) break;
      try {
        ws.send(payload);
      } catch (error) {
        console.warn('WS Hub: Failed to send queued message', error);
        failedCount++;
        // Only re-queue if we haven't exceeded max retries
        if (failedCount < maxRetries) {
          q.unshift(payload);
        } else {
          console.error(`WS Hub: Dropping message after ${maxRetries} failed attempts`, { payload: payload.substring(0, 100) });
        }
        break; // Stop processing queue on first failure
      }
    }

    // If we still have messages in queue after failures, they will be retried on next connection
    if (q.length > 0 && failedCount >= maxRetries) {
      console.warn(`WS Hub: ${q.length} messages still in queue after failures, will retry on reconnection`);
    }
  }

  private surfaceConnectionFailure(name: WSName, reason: string) {
    const conn = this.connections[name];
    conn.failureReason = reason;
    conn.lastFailureTime = Date.now();

    // Dispatch event for UI to show connection failure hint
    try {
      window.dispatchEvent(new CustomEvent("ws:connection_failed", {
        detail: { name, reason, timestamp: conn.lastFailureTime }
      }));
    } catch (error) {
      console.warn('WS Hub: Failed to dispatch connection failure event', error);
    }

    console.warn(`WS ${name}: Connection failed - ${reason}`);
  }

  // Generic connector with per-socket hooks
  private async connect(
    name: WSName,
    path: string,
    onOpenExtra: (ws: WebSocket) => void,
    onMessage: (e: MessageEvent) => void,
    retry = 0
  ) {
    // Check authentication before attempting connection
    const authOrchestrator = getAuthOrchestrator();
    const _state = authOrchestrator.getState();
    const isAuthed = Boolean(_state.is_authenticated);
    const sessionReady = Boolean(_state.session_ready);
    const whoamiOk = Boolean(_state.whoamiOk);

    if (!(isAuthed && sessionReady && whoamiOk)) {
      console.info(`WS ${name}: Skipping connection - not authenticated`);
      this.surfaceConnectionFailure(name, "Not authenticated");
      return;
    }

    // Check backend health to avoid connect attempts during outages
    const healthy = await this.isBackendHealthy();
    if (!healthy) {
      this.surfaceConnectionFailure(name, "Backend not healthy");
      const delay = this.jitteredDelayFor(retry++);
      this.connections[name].timer = setTimeout(() => this.connect(name, path, onOpenExtra, onMessage, retry), delay);
      return;
    }

    // Check if we've exceeded reconnection attempts
    if (retry > 0 && this.connections[name].reconnectAttempts >= this.connections[name].maxReconnectAttempts) {
      console.warn(`WS ${name}: Max reconnection attempts reached (${this.connections[name].reconnectAttempts}/${this.connections[name].maxReconnectAttempts})`);
      this.surfaceConnectionFailure(name, "Max reconnection attempts reached");
      return;
    }

    // Clean any previous socket
    this.safeClose(this.connections[name].socket);

    try {
      const ws = new WebSocket(wsUrl(path), ["json.realtime.v1"]);
      this.connections[name].socket = ws;

      // heartbeat: send ping every 25s
      const heartbeat = () => {
        try { ws.send('ping'); } catch (error) {
          console.warn('WS Hub: Failed to send heartbeat ping', error);
        }
      };

      ws.onopen = () => {
        retry = 0; // reset backoff
        this.connections[name].lastPong = Date.now();
        this.connections[name].reconnectAttempts = 0; // Reset on successful connection
        this.connections[name].failureReason = null; // Clear failure reason
        try { onOpenExtra.call(this, ws); } catch (error) {
          console.warn('WS Hub: onOpenExtra callback failed', error);
        }
        this.flushQueue(name);
        // Clear any existing heartbeat timer and start new one
        if (this.connections[name].heartbeatTimer) {
          clearInterval(this.connections[name].heartbeatTimer);
        }
        this.connections[name].heartbeatTimer = setInterval(heartbeat, 25_000);
      };

      ws.onmessage = (e) => {
        try {
          const raw = String(e.data || "");
          // Handle pong responses first to avoid JSON.parse errors downstream
          if (raw === 'pong') { this.connections[name].lastPong = Date.now(); return; }
          onMessage.call(this, e);
        } catch (error) {
          console.warn('WS Hub: onMessage callback failed, keeping socket alive', error);
        }
      };

      ws.onclose = (event) => {
        // DO NOT call whoami on close - use global auth store instead
        if (this.connections[name].heartbeatTimer) {
          clearInterval(this.connections[name].heartbeatTimer);
          this.connections[name].heartbeatTimer = null;
        }

        // Check if we should attempt reconnection
        const s = authOrchestrator.getState();
        const okAuthed = Boolean(s.is_authenticated);
        const okSession = Boolean(s.session_ready);
        const okWhoami = Boolean(s.whoamiOk);
        if ((okAuthed && okSession && okWhoami) && this.connections[name].reconnectAttempts < this.connections[name].maxReconnectAttempts) {
          this.connections[name].reconnectAttempts += 1;
          const delay = this.jitteredDelayFor(retry++);
          this.connections[name].timer = setTimeout(() => this.connect(name, path, onOpenExtra, onMessage, retry), delay);
        } else {
          // Max attempts reached or not authenticated - surface failure
          if (!(okAuthed && okSession && okWhoami)) {
            this.surfaceConnectionFailure(name, "Connection lost - not authenticated");
          } else {
            this.surfaceConnectionFailure(name, "Connection lost - max reconnection attempts reached");
          }
        }
      };

      ws.onerror = (event) => {
        // Log error but don't surface it immediately - let onclose handle reconnection logic
        console.warn(`WS ${name}: WebSocket connection error`, {
          name,
          readyState: ws.readyState,
          timestamp: new Date().toISOString(),
          event: event
        });
      };

    } catch (error) {
      console.error(`WS ${name}: Failed to create WebSocket connection`, {
        error: error instanceof Error ? error.message : String(error),
        timestamp: new Date().toISOString(),
        name,
        retry
      });
      this.surfaceConnectionFailure(name, "Failed to create connection");
    }
  }

  // ---------------- message handlers ----------------

  private onMusicOpen(ws: WebSocket) {
    // Send initial ping
    try { ws.send('ping'); } catch (error) {
      console.warn('WS Hub: Failed to send initial ping in onMusicOpen', error);
    }
  }

  private onMusicMessage(e: MessageEvent) {
    const raw = String(e.data ?? "");
    if (!raw || raw === 'pong') return;
    let msg: { topic?: string; data?: unknown };
    try { msg = JSON.parse(raw); } catch (error) {
      console.debug('WS Hub: Failed to parse music message JSON', error);
      return;
    }
    const topic = String(msg?.topic || "");
    if (topic === "music.state") {
      (window as any).__musicState = msg.data || {};
      // Broadcast with detail for consumers
      try { window.dispatchEvent(new CustomEvent("music.state", { detail: msg.data || {} })); } catch (error) {
        console.debug('WS Hub: Failed to dispatch music.state event', error);
      }
      return;
    }
    // Fan-out any other music.* topics (e.g., music.queue.updated)
    if (topic.startsWith("music.")) {
      try { window.dispatchEvent(new CustomEvent(topic, { detail: msg.data ?? msg } as any)); } catch (error) {
        console.debug('WS Hub: Failed to dispatch music topic event', error);
      }
    }
  }

  private onCareOpen(ws: WebSocket) {
    try {
      ws.send(JSON.stringify({ action: "subscribe", topic: "resident:me" }));
      // Send initial ping
      ws.send(JSON.stringify({ action: 'ping' }));
    } catch (error) {
      console.warn('WS Hub: Failed to send initial messages in onCareOpen', error);
    }
  }

  private onCareMessage(e: MessageEvent) {
    const raw = String(e.data ?? "");
    if (!raw || raw === 'pong') return;
    let msg: { data?: { event?: string } };
    try { msg = JSON.parse(raw); } catch (error) {
      console.debug('WS Hub: Failed to parse care message JSON', error);
      return;
    }
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
    const ws = this.connections.care.socket;
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.send(payload); } catch (error) {
        console.warn('WS Hub: Failed to send care message, queuing', error);
        this.connections.care.queue.push(payload);
      }
    } else {
      this.connections.care.queue.push(payload);
    }
  }

  sendMusic(data: unknown) {
    const payload = typeof data === "string" ? data : JSON.stringify(data ?? {});
    const ws = this.connections.music.socket;
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.send(payload); } catch (error) {
        console.warn('WS Hub: Failed to send music message, queuing', error);
        this.connections.music.queue.push(payload);
      }
    } else {
      this.connections.music.queue.push(payload);
    }
  }
}

export const wsHub = new WsHub();
