"use client";

import { useEffect } from "react";
import { getSessionState, getToken } from "@/lib/api";
import { wsHub } from "@/services/wsHub";

export default function WsBootstrap() {
    useEffect(() => {
        let started = false;
        let lastReadyEventAt = 0;
        // Initial probe to avoid starting sockets before sessionReady
        // Only check if we have a token
        const hasToken = getToken();

        if (hasToken) {
            (async () => {
                try {
                    const s = await getSessionState();
                    if (s.sessionReady && !started) { wsHub.start({ music: true, care: false }); started = true; }
                } catch { /* noop */ }
            })();
        }
        const onAuthReady = (ev: Event) => {
            try {
                const ready = (ev as CustomEvent).detail?.ready === true;
                const now = Date.now();
                // Debounce duplicate auth:ready flips within 1s to avoid reconnect storms
                if (now - lastReadyEventAt < 1000) return;
                lastReadyEventAt = now;
                if (ready && !started) {
                    try { console.info('WS start reason=auth.ready'); } catch { }
                    wsHub.start({ music: true, care: false });
                    started = true;
                } else if (!ready && started) {
                    try { console.info('WS stop reason=auth.lost'); } catch { }
                    wsHub.stop({ music: true, care: false });
                    started = false;
                }
            } catch { /* noop */ }
        };
        window.addEventListener('auth:ready', onAuthReady as EventListener);
        return () => {
            window.removeEventListener('auth:ready', onAuthReady as EventListener);
            if (started) wsHub.stop({ music: true, care: false });
        };
    }, []);
    return null;
}
