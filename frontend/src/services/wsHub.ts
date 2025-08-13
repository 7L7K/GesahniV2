"use client";

import { wsUrl } from "@/lib/api";

type Closeable = { close: () => void } | null;

class WsHub {
    private music: WebSocket | null = null;
    private care: WebSocket | null = null;
    private timers: { music?: any; care?: any } = {};

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

    private connectMusic(retry = 0) {
        this.safeClose(this.music);
        try {
            const ws = new WebSocket(wsUrl("/v1/ws/music"));
            this.music = ws;
            ws.onopen = () => { retry = 0; };
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
                const delay = Math.min(30000, 500 * Math.pow(2, retry++));
                this.timers.music = setTimeout(() => this.connectMusic(retry), delay);
            };
        } catch {
            const delay = Math.min(30000, 500 * Math.pow(2, retry++));
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
                } catch { }
            };
            ws.onclose = () => {
                const delay = Math.min(30000, 500 * Math.pow(2, retry++));
                this.timers.care = setTimeout(() => this.connectCare(retry), delay);
            };
        } catch {
            const delay = Math.min(30000, 500 * Math.pow(2, retry++));
            this.timers.care = setTimeout(() => this.connectCare(retry), delay);
        }
    }
}

export const wsHub = new WsHub();


