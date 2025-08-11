"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

type CalItem = { time?: string; title?: string };

export default function Calendar() {
    const [items, setItems] = useState<CalItem[]>([]);
    const [muted, setMuted] = useState(false);
    useEffect(() => {
        (async () => {
            try {
                const res = await apiFetch("/v1/tv/calendar/next", { method: "GET" });
                const body = (await res.json()) as { items: CalItem[] };
                setItems(Array.isArray(body.items) ? body.items : []);
            } catch {
                setItems([]);
            }
        })();
    }, []);
    return (
        <main className="min-h-screen bg-black text-white p-8 max-w-4xl mx-auto">
            <h1 className="text-6xl font-bold mb-8">Today</h1>
            <ul className="space-y-4">
                {items.length === 0 && <li className="text-3xl opacity-80">No events found.</li>}
                {items.map((e, i) => (
                    <li key={i} className="bg-zinc-800 rounded-3xl p-6 text-4xl flex items-center gap-6">
                        <div className="w-48 text-right opacity-90">{e.time || ""}</div>
                        <div className="flex-1 font-semibold">{e.title || ""}</div>
                    </li>
                ))}
            </ul>
            <div className="mt-10">
                <button onClick={() => setMuted(m => !m)} className="bg-white text-black px-10 py-6 rounded-3xl text-4xl">
                    {muted ? "Unmute reminders" : "Mute reminders today?"}
                </button>
            </div>
        </main>
    );
}


