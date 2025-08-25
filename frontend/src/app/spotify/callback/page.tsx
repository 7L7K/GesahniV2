'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

export default function SpotifyCallback() {
    const sp = useSearchParams();
    const router = useRouter();
    const [msg, setMsg] = useState('Finalizing…');

    useEffect(() => {
        const code = sp.get('code');
        const state = sp.get('state');
        const error = sp.get('error');
        if (error) {
            setMsg(`Spotify error: ${error}`);
            return;
        }
        if (!code || !state) {
            setMsg('Missing code/state from Spotify.');
            return;
        }
        (async () => {
            const r = await fetch(`/v1/spotify/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`, {
                credentials: 'include',
            });
            const j = await r.json();
            if (!j.ok) throw new Error(j.detail || 'Failed to complete Spotify connect');
            setMsg('Connected! Redirecting…');
            router.replace('/settings/integrations'); // adjust target
        })().catch(err => {
            console.error(err);
            setMsg(err.message || 'Callback failed.');
        });
    }, [sp, router]);

    return (
        <div className="p-8">
            <h1 className="text-xl font-semibold">{msg}</h1>
        </div>
    );
}
