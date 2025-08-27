'use client';

import { useEffect } from 'react';

export default function SpotifyConnectPage() {
    useEffect(() => {
        console.log('🎵 SPOTIFY CONNECT PAGE: Starting Spotify connection process');

        (async () => {
            console.log('🎵 SPOTIFY CONNECT PAGE: Importing API functions...');
            const { apiFetch, getTokens } = await import('@/lib/api');

            console.log('🎵 SPOTIFY CONNECT PAGE: Getting user tokens...');
            const tokens = getTokens();
            console.log('🎵 SPOTIFY CONNECT PAGE: Tokens received:', {
                hasTokens: !!tokens,
                hasAccessToken: !!tokens?.access_token,
                hasRefreshToken: !!tokens?.refresh_token,
                userId: tokens?.user_id,
                tokenLength: tokens?.access_token?.length || 0
            });

            // Start OAuth from authenticated settings handler; backend will read user from session/JWT
            console.log('🎵 SPOTIFY CONNECT PAGE: Starting authenticated connect flow');

            const apiUrl = `/v1/spotify/connect`;
            console.log('🎵 SPOTIFY CONNECT PAGE: Calling API:', apiUrl);

            try {
                const r = await apiFetch(apiUrl, {
                    credentials: 'include',
                    auth: false
                });

                console.log('🎵 SPOTIFY CONNECT PAGE: API response received:', {
                    status: r.status,
                    statusText: r.statusText,
                    ok: r.ok,
                    headers: Object.fromEntries(r.headers.entries())
                });

                if (!r.ok) {
                    console.error('🎵 SPOTIFY CONNECT PAGE: API response not OK');
                    throw new Error(`API returned ${r.status}: ${r.statusText}`);
                }

                const j = await r.json();
                console.log('🎵 SPOTIFY CONNECT PAGE: API JSON response:', j);

                if (!j.ok || !j.authorize_url) {
                    console.error('🎵 SPOTIFY CONNECT PAGE: Invalid response structure');
                    throw new Error(j.detail || 'Failed to start Spotify login - invalid response');
                }

                console.log('🎵 SPOTIFY CONNECT PAGE: Redirecting to Spotify:', j.authorize_url);
                window.location.href = j.authorize_url;

            } catch (apiError) {
                console.error('🎵 SPOTIFY CONNECT PAGE: API call failed:', apiError);
                throw apiError;
            }

        })().catch(err => {
            console.error('🎵 SPOTIFY CONNECT PAGE: Final error:', err);
            alert(`Could not start Spotify connect: ${err.message}. Check console for details.`);
        });
    }, []);

    return (
        <div className="p-8">
            <h1 className="text-2xl font-semibold">Connecting Spotify…</h1>
            <p className="text-sm opacity-70 mt-2">You’ll be redirected to Spotify to approve access.</p>
        </div>
    );
}
