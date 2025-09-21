'use client';

import { useEffect } from 'react';

export default function SpotifyConnectPage() {
    useEffect(() => {
        console.log('🎵 SPOTIFY CONNECT PAGE: Starting Spotify connection process');

        (async () => {
            console.log('🎵 SPOTIFY CONNECT PAGE: Importing API functions...');
            const { apiFetch, getToken } = await import('@/lib/api');

            console.log('🎵 SPOTIFY CONNECT PAGE: Getting user token...');
            const token = getToken();
            console.log('🎵 SPOTIFY CONNECT PAGE: Token received:', {
                hasToken: !!token,
                tokenLength: token?.length || 0
            });

            // Start OAuth from authenticated settings handler; backend will read user from session/JWT
            console.log('🎵 SPOTIFY CONNECT PAGE: Starting authenticated connect flow');

            try {
                const { connectSpotify } = await import('@/lib/api/integrations');
                console.log('🎵 SPOTIFY CONNECT PAGE: Calling connectSpotify...');

                const result = await connectSpotify('/settings#spotify=connected');
                console.log('🎵 SPOTIFY CONNECT PAGE: Connect result:', result);

                if (!result?.authorize_url) {
                    console.error('🎵 SPOTIFY CONNECT PAGE: No authorization URL returned');
                    throw new Error('Failed to get Spotify authorization URL');
                }

                console.log('🎵 SPOTIFY CONNECT PAGE: Redirecting to Spotify:', result.authorize_url);
                window.location.href = result.authorize_url;

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
