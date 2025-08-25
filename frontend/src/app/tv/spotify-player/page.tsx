'use client';

import { useEffect, useState } from 'react';

declare global {
    interface Window {
        onSpotifyWebPlaybackSDKReady: () => void;
        Spotify: any;
    }
}

const ENABLED = process.env.NEXT_PUBLIC_ENABLE_SPOTIFY_WEB_SDK === '1';

export default function TVSpotifyPlayer() {
    const [status, setStatus] = useState(ENABLED ? 'Loading SDK…' : 'Disabled');

    useEffect(() => {
        if (!ENABLED) return;
        const s = document.createElement('script');
        s.src = 'https://sdk.scdn.co/spotify-player.js';
        document.body.appendChild(s);

        window.onSpotifyWebPlaybackSDKReady = async () => {
            setStatus('Initializing…');
            // Get a short-lived access token for the SDK (from purpose-built endpoint)
            const r = await fetch('/v1/spotify/token-for-sdk', { credentials: 'include' });
            const j = await r.json();
            if (!j.ok || !j.access_token) {
                setStatus('Not connected or token missing.');
                return;
            }
            const token: string = j.access_token;

            const player = new window.Spotify.Player({
                name: 'Gesahni TV',
                getOAuthToken: (cb: (t: string) => void) => cb(token),
                volume: 0.8,
            });

            player.addListener('ready', ({ device_id }: any) => {
                setStatus(`Ready • Device ${device_id}`);
                // Optionally: call /v1/spotify/play to target this device_id automatically
                fetch('/v1/spotify/play', {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ device_id }),
                }).catch(() => { });
            });

            player.addListener('initialization_error', ({ message }: any) => setStatus(`Init error: ${message}`));
            player.addListener('authentication_error', ({ message }: any) => setStatus(`Auth error: ${message}`));
            player.addListener('account_error', ({ message }: any) => setStatus(`Account error: ${message}`));
            player.addListener('playback_error', ({ message }: any) => setStatus(`Playback error: ${message}`));

            player.connect();
        };

        return () => { s.remove(); };
    }, []);

    return (
        <div className="p-8">
            <h1 className="text-2xl font-semibold">Spotify on TV</h1>
            <p className="opacity-70 mt-2">{status}</p>
        </div>
    );
}
