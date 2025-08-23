"use client";

import { useEffect, useState } from "react";
import { useSceneManager } from "@/state/sceneManager";
import { emitVibeChanged } from "@/lib/uiIntents";

const VIBES = ["Bright", "Calm", "High Contrast", "Quiet Hours"] as const;

export function VibeSwitcher() {
    const [open, setOpen] = useState(false);
    const [idx, setIdx] = useState(0);
    const { setQuietHours } = useSceneManager();

    useEffect(() => {
        const onLong = () => setOpen((o) => !o);
        const onLeft = () => setIdx((i) => (i + VIBES.length - 1) % VIBES.length);
        const onRight = () => setIdx((i) => (i + 1) % VIBES.length);
        const onOk = () => {
            const vibe = VIBES[idx];
            emitVibeChanged(vibe);
            setOpen(false);
            if (vibe === "Quiet Hours") setQuietHours(true); else setQuietHours(false);
        };
        window.addEventListener("remote:longpress:ok", onLong);
        window.addEventListener("remote:left", onLeft);
        window.addEventListener("remote:right", onRight);
        window.addEventListener("remote:ok", onOk);
        return () => {
            window.removeEventListener("remote:longpress:ok", onLong);
            window.removeEventListener("remote:left", onLeft);
            window.removeEventListener("remote:right", onRight);
            window.removeEventListener("remote:ok", onOk);
        };
    }, [idx, setQuietHours]);

    if (!open) return null;
    return (
        <div className="absolute inset-0 bg-black/70 text-white flex items-center justify-center">
            <div className="bg-white/10 rounded-3xl p-8">
                <div className="text-[48px] font-bold mb-6">Vibe</div>
                <div className="flex gap-4">
                    {VIBES.map((v, i) => (
                        <div key={v} className={`px-6 py-4 rounded-2xl text-[28px] ${i === idx ? 'bg-blue-600' : 'bg-white/10'}`}>{v}</div>
                    ))}
                </div>
            </div>
        </div>
    );
}
