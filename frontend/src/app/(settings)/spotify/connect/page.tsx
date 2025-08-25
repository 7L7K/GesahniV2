'use client';

import { useEffect } from 'react';

export default function SpotifyConnectPage() {
    useEffect(() => {
        (async () => {
            const r = await fetch('/v1/spotify/login', { credentials: 'include' });
            const j = await r.json();
            if (!j.ok) throw new Error(j.detail || 'Failed to start Spotify login');
            window.location.href = j.authorize_url;
        })().catch(err => {
            console.error(err);
            alert('Could not start Spotify connect. Check console.');
        });
    }, []);

    return (
        <div className="p-8">
            <h1 className="text-2xl font-semibold">Connecting Spotify…</h1>
            <p className="text-sm opacity-70 mt-2">You’ll be redirected to Spotify to approve access.</p>
        </div>
    );
}
