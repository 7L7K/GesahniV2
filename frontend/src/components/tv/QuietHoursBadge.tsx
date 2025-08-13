"use client";

import { useSceneManager } from "@/state/sceneManager";

export function QuietHoursBadge() {
    const { isQuietHours } = useSceneManager();
    return (
        <div className="absolute top-6 left-6">
            <div className={`px-5 py-3 rounded-2xl text-[28px] ${isQuietHours ? 'bg-purple-700 text-white' : 'bg-white/10 text-white/80'}`}>
                {isQuietHours ? 'Quiet Hours' : 'Quiet filter off'}
            </div>
        </div>
    );
}


