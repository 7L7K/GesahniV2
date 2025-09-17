"use client";

import React from "react";
import { listDevices, setDevice } from "@/lib/api";

interface Device {
    id: string;
    name: string;
    type: string;
    is_active: boolean;
}

export default function DevicePicker() {
    const [devices, setDevices] = React.useState<Device[]>([]);
    const [loading, setLoading] = React.useState(false);
    const refresh = async () => {
        setLoading(true);
        try {
            const r = await listDevices();
            setDevices(r.devices || []);
        } finally {
            setLoading(false);
        }
    };
    React.useEffect(() => { refresh(); }, []);
    const pick = async (id: string) => {
        await setDevice(id);
    };
    if (!devices.length) return null;
    return (
        <div className="rounded-xl bg-card p-3 shadow">
            <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-medium">Playback Device</div>
                <button className="text-xs text-muted-foreground" onClick={refresh} disabled={loading}>Refresh</button>
            </div>
            <div className="space-y-1">
                {devices.map((d) => (
                    <button key={d.id} onClick={() => pick(d.id)} className="w-full text-left text-sm px-2 py-1 rounded hover:bg-muted">
                        {d.name} {d.is_active ? "•" : ""}
                    </button>
                ))}
            </div>
        </div>
    );
}
