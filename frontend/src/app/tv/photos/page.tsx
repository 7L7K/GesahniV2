"use client";

import { useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";

export default function Photos() {
    const ref = useRef<HTMLImageElement>(null);
    const [items, setItems] = useState<string[]>([]);
    const [folder, setFolder] = useState<string>("/shared_photos");
    const [idx, setIdx] = useState(0);
    const [paused, setPaused] = useState(false);
    const [status, setStatus] = useState<string>("");
    useEffect(() => {
        (async () => {
            try {
                const res = await apiFetch("/v1/tv/photos", { method: "GET" });
                const body = (await res.json()) as { folder: string; items: string[] };
                setFolder(body.folder || "/shared_photos");
                setItems(Array.isArray(body.items) ? body.items : []);
            } catch {
                setStatus("Offline. Showing cached photos if available.");
            }
        })();
    }, []);

    useEffect(() => {
        if (!items.length) return;
        if (!ref.current) return;
        ref.current.src = `${folder}/${items[idx % items.length]}`;
    }, [idx, items, folder]);

    useEffect(() => {
        if (!items.length) return;
        const id = setInterval(() => {
            if (!paused) setIdx((i) => i + 1);
        }, 5000);
        return () => clearInterval(id);
    }, [items, paused]);

    const next = () => setIdx((i) => i + 1);
    const prev = () => setIdx((i) => (i - 1 + Math.max(1, items.length)) % Math.max(1, items.length));
    const fav = async () => {
        const name = items[idx % Math.max(1, items.length)];
        try {
            await apiFetch(`/v1/tv/photos/favorite`, { method: "POST", body: JSON.stringify({ name }) });
            setStatus("Favorited");
            setTimeout(() => setStatus(""), 1500);
        } catch { }
    };
    return (
        <main className="min-h-screen bg-black text-white flex flex-col items-center justify-center gap-6">
            <img ref={ref} alt="Slideshow" className="max-h-[80vh] object-contain" />
            <div className="flex gap-6 text-4xl">
                <button onClick={prev} className="bg-zinc-800 px-8 py-5 rounded-3xl">⟵ Back</button>
                <button onClick={() => setPaused(p => !p)} className="bg-white text-black px-8 py-5 rounded-3xl">{paused ? "▶ Resume" : "⏸ Pause"}</button>
                <button onClick={next} className="bg-zinc-800 px-8 py-5 rounded-3xl">Next ⟶</button>
                <button onClick={fav} className="bg-blue-600 px-8 py-5 rounded-3xl">★ Favorite</button>
            </div>
            {status && <div className="text-2xl opacity-90">{status}</div>}
        </main>
    );
}
