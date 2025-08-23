"use client";

import { apiFetch } from "@/lib/api";
import { getAuthOrchestrator } from "@/services/authOrchestrator";

export function attachUiEffects() {
    const onDuck = async () => {
        // Only make music API calls when authenticated
        const authState = getAuthOrchestrator().getState();
        if (!authState.is_authenticated) return;

        try { await apiFetch("/v1/music", { method: "POST", body: JSON.stringify({ command: "volume", volume: 10, temporary: true }) }); } catch { }
    };
    const onRestore = async () => {
        // Only make music API calls when authenticated
        const authState = getAuthOrchestrator().getState();
        if (!authState.is_authenticated) return;

        try { await apiFetch("/v1/music/restore", { method: "POST" }); } catch { }
    };
    const onVibe = async (e: Event) => {
        // Only make music API calls when authenticated
        const authState = getAuthOrchestrator().getState();
        if (!authState.is_authenticated) return;

        const detail = (e as CustomEvent).detail || {};
        const name = String(detail.vibe || "");
        if (!name) return;
        try { await apiFetch("/v1/vibe", { method: "POST", body: JSON.stringify({ name }) }); } catch { }
    };
    const onRemoteOk = async () => {
        // Only make music API calls when authenticated
        const authState = getAuthOrchestrator().getState();
        if (!authState.is_authenticated) return;

        try {
            const st = (window as any).__musicState || {};
            const playing = Boolean(st.is_playing || st.playing);
            const cmd = playing ? "pause" : "play";
            await apiFetch("/v1/music", { method: "POST", body: JSON.stringify({ command: cmd }) });
        } catch { }
    };
    const onRemoteUp = () => { window.dispatchEvent(new CustomEvent("alert:confirm")); };
    const onRemoteDown = () => { window.dispatchEvent(new CustomEvent("alert:cancel")); };

    window.addEventListener("ui.duck", onDuck);
    window.addEventListener("ui.restore", onRestore);
    window.addEventListener("ui.vibe.changed", onVibe as EventListener);
    window.addEventListener("remote:ok", onRemoteOk);
    window.addEventListener("remote:up", onRemoteUp);
    window.addEventListener("remote:down", onRemoteDown);

    return () => {
        window.removeEventListener("ui.duck", onDuck);
        window.removeEventListener("ui.restore", onRestore);
        window.removeEventListener("ui.vibe.changed", onVibe as EventListener);
        window.removeEventListener("remote:ok", onRemoteOk);
        window.removeEventListener("remote:up", onRemoteUp);
        window.removeEventListener("remote:down", onRemoteDown);
    };
}
