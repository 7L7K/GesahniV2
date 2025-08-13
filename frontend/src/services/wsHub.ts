"use client";

import { wsUrl } from "@/lib/api";

type Closeable = { close: () => void } | null;

class WsHub {
    private music: WebSocket | null = null;
    private care: WebSocket | null = null;
    private timers: { music?: any; care?: any } = {};
    private queues: { music: any[]; care: any[] } = { music: [], care: [] };

    start() {
        this.connectMusic();
        this.connectCare();
    }

    stop() {
        this.safeClose(this.music); this.music = null;
        this.safeClose(this.care); this.care = null;
        if (this.timers.music) clearTimeout(this.timers.music);
        if (this.timers.care) clearTimeout(this.timers.care);
    }

    private safeClose(ws: Closeable) { try { ws && ws.close(); } catch { } }

    private jitteredDelayFor(retry: number) {
        const base = Math.min(30000, 500 * Math.pow(2, retry));
        const jitter = base * (0.15 * (Math.random() * 2 - 1)); // ±15%
        return Math.max(250, Math.floor(base + jitter));
    }

    private flushQueue(which: 'music' | 'care') {
        const ws = which === 'music' ? this.music : this.care;
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        const q = this.queues[which];
        while (q.length) {
            try { ws.send(q.shift()); } catch { break; }
        }
    }

    sendCare(data: any) {
        const payload = typeof data === 'string' ? data : JSON.stringify(data);
        if (this.care && this.care.readyState === WebSocket.OPEN) {
            try { this.care.send(payload); } catch { this.queues.care.push(payload); }
        } else {
            this.queues.care.push(payload);
        }
    }

    sendMusic(data: any) {
        const payload = typeof data === 'string' ? data : JSON.stringify(data);
        if (this.music && this.music.readyState === WebSocket.OPEN) {
            try { this.music.send(payload); } catch { this.queues.music.push(payload); }
        } else {
            this.queues.music.push(payload);
        }
    }

    private connectMusic(retry = 0) {
        this.safeClose(this.music);
        try {
            const ws = new WebSocket(wsUrl("/v1/ws/music"));
            this.music = ws;
            ws.onopen = () => { retry = 0; this.flushQueue('music'); };
            ws.onmessage = (e) => {
                try {
                    const msg = JSON.parse(String(e.data || ""));
                    if (msg && msg.topic === "music.state") {
                        (window as any).__musicState = msg.data || {};
                        window.dispatchEvent(new CustomEvent("music.state"));
                    }
                } catch { }
            };
            ws.onclose = () => {
                const delay = this.jitteredDelayFor(retry++);
                this.timers.music = setTimeout(() => this.connectMusic(retry), delay);
            };
        } catch {
            const delay = this.jitteredDelayFor(retry++);
            this.timers.music = setTimeout(() => this.connectMusic(retry), delay);
        }
    }

    private connectCare(retry = 0) {
        this.safeClose(this.care);
        try {
            const ws = new WebSocket(wsUrl("/v1/ws/care"));
            this.care = ws;
            ws.onopen = () => {
                retry = 0;
                try { ws.send(JSON.stringify({ action: "subscribe", topic: "resident:me" })); } catch { }
                this.flushQueue('care');
            };
            ws.onmessage = (e) => {
                try {
                    const msg = JSON.parse(String(e.data || ""));
                    const data = msg?.data || {};
                    const event = String(data.event || "");
                    if (event.startsWith("alert.")) {
                        window.dispatchEvent(new CustomEvent("alert:incoming", { detail: data } as any));
                    }
                    if (event === "device.heartbeat") {
                        (window as any).__deviceHeartbeatAt = Date.now();
                        window.dispatchEvent(new CustomEvent("device.heartbeat"));
                    }
                    if (event === "tv.config.updated") {
                        // Broadcast a UI event so components can react and hot-apply config
                        (window as any).__tvConfigLastUpdatedAt = Date.now();
                        window.dispatchEvent(new CustomEvent("tv.config.updated", { detail: data } as any));
                    }
                } catch { }
            };
            ws.onclose = () => {
                const delay = this.jitteredDelayFor(retry++);
                this.timers.care = setTimeout(() => this.connectCare(retry), delay);
            };
        } catch {
            const delay = this.jitteredDelayFor(retry++);
            this.timers.care = setTimeout(() => this.connectCare(retry), delay);
        }
    }
}

export const wsHub = new WsHub();


