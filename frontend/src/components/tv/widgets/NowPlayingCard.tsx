"use client";

import { useEffect, useState } from "react";

type MusicState = { title?: string; artist?: string; playing?: boolean };

export function NowPlayingCard() {
    const [state, setState] = useState<MusicState>({});
    useEffect(() => {
        const update = () => setState((window as any).__musicState || {});
        update();
        const t = setInterval(update, 2000);
        return () => clearInterval(t);
    }, []);
    const { title = "Nothing playing", artist = "", playing = false } = state;
    return (
        <div className="text-white w-full flex items-center gap-6">
            <div className="w-40 h-40 bg-white/10 rounded-2xl" />
            <div className="flex-1">
                <div className="text-[48px] font-semibold">{title}</div>
                <div className="text-[28px] opacity-80">{artist}</div>
            </div>
            <div className="text-[28px] opacity-80">{playing ? "Playing" : "Paused"}</div>
        </div>
    );
}


