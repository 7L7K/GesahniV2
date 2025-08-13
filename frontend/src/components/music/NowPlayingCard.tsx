"use client";

import React from "react";
import Image from "next/image";
import { musicCommand, type MusicState } from "@/lib/api";
import { Button } from "@/components/ui/button";

export default function NowPlayingCard({ state }: { state: MusicState }) {
    const { track, is_playing } = state;
    const art = track?.art_url || "/placeholder.png";
    const onPlayPause = async () => {
        await musicCommand({ command: is_playing ? "pause" : "play" });
    };
    const onNext = async () => {
        await musicCommand({ command: "next" });
    };
    const onPrev = async () => {
        await musicCommand({ command: "previous" });
    };

    return (
        <div className="rounded-xl bg-card p-4 shadow">
            <div className="flex gap-4 items-center">
                <div className="w-24 h-24 relative overflow-hidden rounded-md">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={art || ""} alt={track?.name || "art"} className="w-full h-full object-cover" />
                </div>
                <div className="flex-1 min-w-0">
                    <div className="text-base font-semibold truncate">{track?.name || "Nothing playing"}</div>
                    <div className="text-sm text-muted-foreground truncate">{track?.artists || "—"}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                        {state.provider === 'spotify' ? 'Spotify' : (state.provider === 'radio' ? 'Radio' : '—')}
                    </div>
                    {!state.explicit_allowed && (
                        <div className="mt-1 text-[11px] text-amber-600">Explicit content filtered</div>
                    )}
                    {state.quiet_hours && (
                        <div className="mt-0.5 text-[11px] text-amber-600">Quiet hours cap</div>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <Button variant="ghost" onClick={onPrev} aria-label="Previous">⏮</Button>
                    <Button onClick={onPlayPause} aria-label="Play/Pause">{is_playing ? "⏸" : "▶"}</Button>
                    <Button variant="ghost" onClick={onNext} aria-label="Next">⏭</Button>
                </div>
            </div>
        </div>
    );
}


