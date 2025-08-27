'use client';

import { useEffect, useState } from 'react';

type Device = { id: string; name: string; type: string; is_active: boolean; };

export default function SpotifyControls() {
    const [devices, setDevices] = useState<Device[]>([]);
    const [loading, setLoading] = useState(false);
    const [uri, setUri] = useState('spotify:track:4cOdK2wGLETKBW3PvgPWqT'); // test

    const refreshDevices = async () => {
        const { apiFetch } = await import('@/lib/api');
        const r = await apiFetch('/v1/spotify/devices', { credentials: 'include', auth: true });
        const j = await r.json();
        if (j.ok) setDevices(j.devices || []);
    };

    useEffect(() => { refreshDevices(); }, []);

    const play = async (device_id?: string) => {
        setLoading(true);
        try {
            const { apiFetch } = await import('@/lib/api');
            const r = await apiFetch('/v1/spotify/play', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ uris: [uri], device_id }),
                auth: true,
            });
            if (r.status === 403) alert('Premium required for playback.');
            if (r.status === 429) alert('Rate limited—try again shortly.');
            if (!r.ok && r.status !== 403 && r.status !== 429) alert('Play failed.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="space-y-3 p-4 rounded-2xl border shadow-sm">
            <div className="flex items-center gap-2">
                <input className="flex-1 border rounded px-2 py-1" value={uri} onChange={e => setUri(e.target.value)} />
                <button className="px-3 py-1 rounded bg-black text-white" onClick={() => play()}>
                    {loading ? 'Playing…' : 'Play on active'}
                </button>
            </div>
            <div>
                <div className="flex items-center justify-between">
                    <h3 className="font-medium">Devices</h3>
                    <button className="text-sm underline" onClick={refreshDevices}>Refresh</button>
                </div>
                <ul className="mt-2 space-y-1">
                    {devices.map(d => (
                        <li key={d.id} className="flex items-center justify-between rounded border p-2">
                            <div>
                                <div className="font-medium">{d.name}</div>
                                <div className="text-xs opacity-70">{d.type}{d.is_active ? ' • active' : ''}</div>
                            </div>
                            <button className="text-sm px-2 py-1 rounded bg-neutral-900 text-white" onClick={() => play(d.id)}>
                                Play here
                            </button>
                        </li>
                    ))}
                    {devices.length === 0 && <li className="text-sm opacity-70">No devices. Open Spotify app or enable the Web Player.</li>}
                </ul>
            </div>
        </div>
    );
}
