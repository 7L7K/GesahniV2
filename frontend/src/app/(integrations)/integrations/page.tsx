'use client';

import dynamic from 'next/dynamic';

const SpotifyControls = dynamic(() => import('@/components/music/SpotifyControls'), { ssr: false });

export default function IntegrationsPage() {
    return (
        <div className="p-8 space-y-6">
            <header>
                <h1 className="text-2xl font-bold">Integrations</h1>
                <p className="text-sm opacity-70">Manage and test connected services.</p>
            </header>

            <section className="space-y-2">
                <div className="flex items-center justify-between">
                    <h2 className="text-lg font-semibold">Spotify</h2>
                    <a
                        href="/spotify/connect"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm underline"
                        onClick={() => {
                            console.log('🎵 INTEGRATIONS PAGE: Spotify connect link clicked');
                            console.log('🎵 INTEGRATIONS PAGE: Opening URL:', '/spotify/connect');
                        }}
                    >
                        Connect / Reconnect
                    </a>
                </div>
                <SpotifyControls />
                <p className="text-xs opacity-60">
                    Tip: If you don’t see a device, open the Spotify app (phone/desktop) or try the TV Web Player.
                </p>
            </section>
        </div>
    );
}
