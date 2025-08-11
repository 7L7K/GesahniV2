"use client";

import { useEffect, useState } from "react";

export function DevicePicker({ onChange }: { onChange: (ids: { audio?: string; video?: string }) => void }) {
    const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
    const [audioId, setAudioId] = useState<string>("");
    const [videoId, setVideoId] = useState<string>("");

    useEffect(() => {
        navigator.mediaDevices.enumerateDevices().then(setDevices).catch(() => setDevices([]));
    }, []);

    useEffect(() => {
        onChange({ audio: audioId || undefined, video: videoId || undefined });
    }, [audioId, videoId, onChange]);

    const audios = devices.filter((d) => d.kind === "audioinput");
    const videos = devices.filter((d) => d.kind === "videoinput");

    return (
        <div className="flex gap-3 text-sm">
            <select value={audioId} onChange={(e) => setAudioId(e.target.value)} className="border rounded px-2 py-1">
                <option value="">Default Mic</option>
                {audios.map((d) => (
                    <option key={d.deviceId} value={d.deviceId}>{d.label || `Mic ${d.deviceId.slice(0, 6)}`}</option>
                ))}
            </select>
            <select value={videoId} onChange={(e) => setVideoId(e.target.value)} className="border rounded px-2 py-1">
                <option value="">Default Camera</option>
                {videos.map((d) => (
                    <option key={d.deviceId} value={d.deviceId}>{d.label || `Cam ${d.deviceId.slice(0, 6)}`}</option>
                ))}
            </select>
        </div>
    );
}


