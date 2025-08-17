"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { getAuthOrchestrator } from "@/services/authOrchestrator";

export default function Music() {
    const presets = ["Gospel Mornings", "Quiet Afternoons", "Night Jazz"];
    const [status, setStatus] = useState<string>("");
    const play = async (p: string) => {
        // Only make music API calls when authenticated
        const authState = getAuthOrchestrator().getState();
        if (!authState.isAuthenticated) {
            setStatus("Not authenticated. Please log in.");
            return;
        }

        try {
            await apiFetch(`/v1/tv/music/play?preset=${encodeURIComponent(p)}`, { method: "POST" });
            setStatus(`Playing: ${p}`);
        } catch {
            setStatus("Offline. Couldn't start playback.");
        }
    };
    return (
        <main className="min-h-screen bg-black text-white p-8 max-w-4xl mx-auto">
            <h1 className="text-6xl font-bold mb-8">Play Music</h1>
            <div className="space-y-5">
                {presets.map(p => (
                    <button key={p} onClick={() => play(p)} className="w-full bg-zinc-800 p-8 rounded-3xl text-left text-4xl focus:outline-none focus:ring-8 focus:ring-blue-500">▶ {p}</button>
                ))}
            </div>
            <div className="mt-10 flex gap-6">
                <button className="bg-white text-black px-10 py-6 rounded-3xl text-4xl">⏯ Play/Pause</button>
                <button className="bg-zinc-700 px-10 py-6 rounded-3xl text-4xl">⏭ Next</button>
            </div>
            {status && <div className="mt-8 text-3xl opacity-90">{status}</div>}
        </main>
    );
}


