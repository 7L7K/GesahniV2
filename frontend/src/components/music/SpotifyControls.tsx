'use client';

import { useEffect, useState } from 'react';

type Device = { id: string; name: string; type: string; is_active: boolean; };

export default function SpotifyControls() {
    const [devices, setDevices] = useState<Device[]>([]);
    const [loading, setLoading] = useState(false);
    const [uri, setUri] = useState('spotify:track:4cOdK2wGLETKBW3PvgPWqT'); // test

    const refreshDevices = async () => {
        console.log('🎵 SPOTIFY CONTROLS: Starting device refresh');

        // Gate device fetch on backend online OR recent whoami success
        try {
            console.log('🎵 SPOTIFY CONTROLS: Checking auth orchestrator state...');
            const { getAuthOrchestrator } = await import('@/services/authOrchestrator');
            const auth = getAuthOrchestrator().getState();
            const last = Number(auth.lastChecked || 0);
            const recent = last && (Date.now() - last) < 60_000;

            console.log('🎵 SPOTIFY CONTROLS: Auth state check', {
                isAuthenticated: auth.is_authenticated,
                sessionReady: auth.session_ready,
                lastChecked: new Date(last).toISOString(),
                recent: recent,
                canProceed: auth.is_authenticated && (recent || auth.session_ready),
                timestamp: new Date().toISOString()
            });

            if (!(auth.is_authenticated && (recent || auth.session_ready))) {
                console.warn('🎵 SPOTIFY CONTROLS: Auth gate blocked device fetch');
                return;
            }
        } catch (authError) {
            console.warn('🎵 SPOTIFY CONTROLS: Auth check failed, proceeding anyway:', authError);
        }

        try {
            console.log('🎵 SPOTIFY CONTROLS: Fetching devices from API...');
            const { apiFetch } = await import('@/lib/api');
            const r = await apiFetch('/v1/spotify/devices', { credentials: 'include', auth: true });

            console.log('🎵 SPOTIFY CONTROLS: Devices API response', {
                status: r.status,
                statusText: r.statusText,
                ok: r.ok,
                headers: Object.fromEntries(r.headers.entries()),
                timestamp: new Date().toISOString()
            });

            const j = await r.json();
            console.log('🎵 SPOTIFY CONTROLS: Devices API JSON response', j);

            if (j.ok) {
                const deviceList = j.devices || [];
                console.log('🎵 SPOTIFY CONTROLS: Setting devices', {
                    count: deviceList.length,
                    devices: deviceList.map((d: Device) => ({ id: d.id, name: d.name, type: d.type, is_active: d.is_active })),
                    timestamp: new Date().toISOString()
                });
                setDevices(deviceList);
            } else {
                console.warn('🎵 SPOTIFY CONTROLS: API response not OK', j);
            }
        } catch (error) {
            console.error('🎵 SPOTIFY CONTROLS: Device fetch failed', error);
        }
    };

    useEffect(() => { refreshDevices(); }, []);

    const play = async (device_id?: string) => {
        console.log('🎵 SPOTIFY CONTROLS: Starting play command', {
            uri: uri,
            deviceId: device_id,
            hasDeviceId: !!device_id,
            timestamp: new Date().toISOString()
        });

        setLoading(true);
        try {
            const requestBody = { uris: [uri], device_id };
            console.log('🎵 SPOTIFY CONTROLS: Play request payload', requestBody);

            const { apiFetch } = await import('@/lib/api');
            const r = await apiFetch('/v1/spotify/play', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody),
                auth: true,
            });

            console.log('🎵 SPOTIFY CONTROLS: Play API response', {
                status: r.status,
                statusText: r.statusText,
                ok: r.ok,
                headers: Object.fromEntries(r.headers.entries()),
                timestamp: new Date().toISOString()
            });

            if (r.status === 403) {
                console.warn('🎵 SPOTIFY CONTROLS: Premium required for playback');
                alert('Premium required for playback.');
            }
            if (r.status === 429) {
                console.warn('🎵 SPOTIFY CONTROLS: Rate limited');
                alert('Rate limited—try again shortly.');
            }
            if (!r.ok && r.status !== 403 && r.status !== 429) {
                console.error('🎵 SPOTIFY CONTROLS: Play failed with unexpected status');
                alert('Play failed.');
            }

            if (r.ok) {
                console.log('🎵 SPOTIFY CONTROLS: Play command successful');
            }
        } catch (error) {
            console.error('🎵 SPOTIFY CONTROLS: Play command failed with exception', error);
            alert('Play failed with error.');
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
