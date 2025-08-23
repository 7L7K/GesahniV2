"use client";

import { useRecorderCtx } from "./RecorderProvider";

export function RecorderControls() {
    const rec = useRecorderCtx();
    const recording = rec.state.status === "recording";
    return (
        <div className="flex items-center justify-center gap-4">
            {!recording ? (
                <button onClick={rec.start} className="group relative w-20 h-20 bg-gradient-to-r from-green-500 to-emerald-600 rounded-full shadow-2xl hover:shadow-green-500/25 transition-all duration-300 hover:scale-105 flex items-center justify-center">
                    <div className="w-8 h-8 bg-white rounded-full flex items-center justify-center">
                        <div className="w-0 h-0 border-l-[12px] border-l-white border-t-[8px] border-t-transparent border-b-[8px] border-b-transparent ml-1"></div>
                    </div>
                    <div className="absolute inset-0 rounded-full bg-white/20 animate-ping"></div>
                </button>
            ) : (
                <button onClick={rec.stop} className="group relative w-20 h-20 bg-gradient-to-r from-red-500 to-pink-600 rounded-full shadow-2xl hover:shadow-red-500/25 transition-all duration-300 hover:scale-105 flex items-center justify-center">
                    <div className="w-8 h-8 bg-white rounded-full flex items-center justify-center">
                        <div className="w-4 h-4 bg-red-500 rounded-sm"></div>
                    </div>
                </button>
            )}
            <button onClick={rec.pause} disabled={!recording} className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 ${recording ? 'bg-gray-100 text-gray-700 hover:bg-gray-200' : 'bg-gray-50 text-gray-400 cursor-not-allowed'}`}>⏸️ Pause</button>
            <button onClick={rec.toggleMute} className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 ${rec.muted ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}>{rec.muted ? '🔇 Muted' : '🔊 Mute'}</button>
            <button onClick={rec.reset} className="flex items-center gap-2 px-4 py-2 rounded-full bg-gray-50 text-gray-700 hover:bg-gray-100 text-sm font-medium transition-all duration-200">🗑️ Reset</button>
        </div>
    );
}
