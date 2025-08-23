"use client";

import { useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { useSceneManager } from "@/state/sceneManager";
import { emitUiDuck, emitUiRestore } from "@/lib/uiIntents";

export function AlertPanel() {
    const scene = useSceneManager();
    const [seconds, setSeconds] = useState(10);
    const [note, setNote] = useState<string>("");
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

    useEffect(() => {
        emitUiDuck();
        scene.toAlert("ws_alert");
        if (timerRef.current) clearInterval(timerRef.current);
        setSeconds(10);
        timerRef.current = setInterval(() => setSeconds((s) => (s > 0 ? s - 1 : 0)), 1000);
        return () => { if (timerRef.current) clearInterval(timerRef.current); emitUiRestore(); };
    }, []);

    const cancel = () => {
        scene.toAmbient("user_interaction");
    };

    const confirm = async () => {
        try { await apiFetch("/v1/tv/alert", { method: "POST", body: JSON.stringify({ kind: "help", note }) }); } catch { }
        scene.toAmbient("user_interaction");
    };

    const pct = (seconds / 10) * 100;

    return (
        <div className="absolute inset-0 bg-black/80 text-white flex flex-col items-center justify-center p-12">
            <div className="text-[64px] font-bold">Alert</div>
            <div className="text-[32px] opacity-90 mt-4">Sending help in {seconds}s…</div>
            <div className="w-[60vw] h-4 bg-white/20 rounded-full mt-6 overflow-hidden">
                <div className="h-full bg-red-500" style={{ width: `${pct}%`, transition: "width 0.3s linear" }} />
            </div>
            <div className="mt-8 flex gap-6">
                <button onClick={confirm} className="bg-red-600 hover:bg-red-700 px-10 py-6 rounded-2xl text-[32px]">Confirm</button>
                <button onClick={cancel} className="bg-white/20 hover:bg-white/30 px-10 py-6 rounded-2xl text-[32px]">Cancel</button>
            </div>
            <div className="mt-6 w-[60vw]">
                <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a note" className="w-full bg-white/10 px-4 py-3 rounded-xl text-[28px] outline-none" />
            </div>
        </div>
    );
}
