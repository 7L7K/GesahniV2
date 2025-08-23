"use client";

import { useEffect, useMemo, useState } from "react";
import { useRecorder } from "@/components/recorder/useRecorder";
import { YesNoBar } from "@/components/tv/YesNoBar";
import { CaptionBar } from "@/components/tv/CaptionBar";
import { apiFetch } from "@/lib/api";

export default function Listening() {
    const { state, captionText, start, stop, reset } = useRecorder();
    const [status, setStatus] = useState<string>("");
    const isRecording = state.status === "recording";

    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (e.code === "Space") {
                e.preventDefault();
                isRecording ? stop() : start();
            }
            if (e.key.toLowerCase() === "escape") {
                stop();
            }
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [isRecording, start, stop]);

    const onYes = async () => {
        setStatus("Confirmed.");
        reset();
    };
    const onNo = () => {
        setStatus("Okay, canceled.");
        reset();
    };
    const help = async () => {
        try {
            await apiFetch("/v1/tv/alert", { method: "POST", body: JSON.stringify({ kind: "help" }) });
            setStatus("Help is on the way.");
        } catch {
            setStatus("Could not reach caregiver.");
        }
    };

    const caption = useMemo(() => captionText || "(waiting)", [captionText]);

    return (
        <main className="min-h-screen bg-black text-white flex flex-col items-center justify-center gap-8">
            <div className="text-6xl font-bold">Listening…</div>
            <div className="text-3xl opacity-90">You said: <span className="font-mono">{caption}</span></div>
            <div className="flex gap-8 mt-2">
                {!isRecording ? (
                    <button onClick={() => start()} className="bg-blue-600 px-12 py-8 rounded-3xl text-4xl">Hold to Talk</button>
                ) : (
                    <button onClick={() => stop()} className="bg-zinc-700 px-12 py-8 rounded-3xl text-4xl">Stop</button>
                )}
                <button onClick={help} className="bg-red-700 px-12 py-8 rounded-3xl text-4xl">Help me</button>
            </div>
            <YesNoBar onYes={onYes} onNo={onNo} />
            <CaptionBar text={captionText} />
            {status && <div className="text-3xl opacity-90">{status}</div>}
        </main>
    );
}
