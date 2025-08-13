"use client";

import React from "react";
import { setVibe } from "@/lib/api";

type Preset = {
    name: string;
    energy: number;
    tempo: number;
    explicit: boolean;
};

const PRESETS: Preset[] = [
    { name: "Calm Night", energy: 0.25, tempo: 80, explicit: false },
    { name: "Uplift Morning", energy: 0.6, tempo: 110, explicit: true },
    { name: "Turn Up", energy: 0.9, tempo: 128, explicit: true },
];

export default function MoodDial() {
    const [idx, setIdx] = React.useState(0);
    const current = PRESETS[idx];

    const rotate = async (dir: 1 | -1) => {
        const next = (idx + dir + PRESETS.length) % PRESETS.length;
        setIdx(next);
        const v = PRESETS[next];
        await setVibe({ name: v.name, energy: v.energy, tempo: v.tempo, explicit: v.explicit });
    };

    return (
        <div className="rounded-xl bg-card p-4 shadow flex items-center gap-4">
            <button className="text-2xl" onClick={() => rotate(-1)} aria-label="Prev vibe">⟲</button>
            <div className="flex-1">
                <div className="text-sm text-muted-foreground">Vibe</div>
                <div className="text-base font-semibold">{current.name}</div>
                <div className="text-xs text-muted-foreground">Energy {(current.energy * 100) | 0} · {current.tempo} bpm</div>
            </div>
            <button className="text-2xl" onClick={() => rotate(1)} aria-label="Next vibe">⟳</button>
        </div>
    );
}


