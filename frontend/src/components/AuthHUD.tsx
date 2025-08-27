'use client';

import { useEffect, useState } from 'react';

interface WhoamiResponse {
    user_id?: string;
    email?: string;
    is_authenticated?: boolean;
    session_ready?: boolean;
    source?: string;
    error?: string;
}

export default function AuthHUD() {
    const [whoamiData, setWhoamiData] = useState<WhoamiResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        // Only show in development
        if (process.env.NODE_ENV !== 'development') {
            return;
        }

        const fetchWhoami = async () => {
            try {
                setLoading(true);
                setError(null);

                const API_URL = process.env.NEXT_PUBLIC_API_ORIGIN || "http://localhost:8000";
                const response = await fetch(`${API_URL}/v1/whoami`, {
                    credentials: 'include'
                });

                console.log('🔐 AUTH HUD: whoami call', {
                    status: response.status,
                    statusText: response.statusText,
                    ok: response.ok,
                    url: response.url,
                    headers: Object.fromEntries(response.headers.entries())
                });

                const data = await response.text();
                console.log('🔐 AUTH HUD: whoami response body:', data);

                let parsedData: WhoamiResponse;
                try {
                    parsedData = JSON.parse(data);
                } catch {
                    parsedData = { error: data };
                }

                setWhoamiData(parsedData);
            } catch (err) {
                console.error('🔐 AUTH HUD: whoami error:', err);
                setError(err instanceof Error ? err.message : String(err));
            } finally {
                setLoading(false);
            }
        };

        fetchWhoami();

        // Refresh every 5 seconds
        const interval = setInterval(fetchWhoami, 5000);
        return () => clearInterval(interval);
    }, []);

    // Don't render anything in production
    if (process.env.NODE_ENV !== 'development') {
        return null;
    }

    return (
        <div
            style={{
                position: 'fixed',
                top: '10px',
                right: '10px',
                background: 'rgba(0, 0, 0, 0.8)',
                color: 'white',
                padding: '10px',
                borderRadius: '5px',
                fontSize: '12px',
                fontFamily: 'monospace',
                zIndex: 9999,
                maxWidth: '300px',
                boxShadow: '0 0 10px rgba(0,0,0,0.5)'
            }}
        >
            <div style={{ marginBottom: '8px', fontWeight: 'bold', color: '#00ff00' }}>
                🔐 AUTH HUD (DEV ONLY)
            </div>

            {loading && (
                <div style={{ color: '#ffff00' }}>
                    🔄 Loading...
                </div>
            )}

            {error && (
                <div style={{ color: '#ff4444' }}>
                    ❌ Error: {error}
                </div>
            )}

            {whoamiData && (
                <div style={{ lineHeight: '1.4' }}>
                    <div>Status: {whoamiData.is_authenticated ? '✅' : '❌'} Auth</div>
                    <div>Session: {whoamiData.session_ready ? '✅' : '❌'} Ready</div>
                    <div>User ID: {whoamiData.user_id || 'none'}</div>
                    <div>Email: {whoamiData.email || 'none'}</div>
                    <div>Source: {whoamiData.source || 'unknown'}</div>
                    {whoamiData.error && (
                        <div style={{ color: '#ff4444', marginTop: '4px' }}>
                            Error: {whoamiData.error}
                        </div>
                    )}
                </div>
            )}

            <div style={{ marginTop: '8px', fontSize: '10px', color: '#888' }}>
                Auto-refreshes every 5s
            </div>
        </div>
    );
}
