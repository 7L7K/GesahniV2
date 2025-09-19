'use client';
import { useEffect, useState } from 'react';
import { getAuthOrchestrator } from '@/services/authOrchestrator';
import { apiFetch } from '@/lib/api/fetch';

export default function AuthDebug() {
    const [r, setR] = useState<any>({});

    useEffect(() => {
        (async () => {
            // Default behavior: use orchestrator
            const id = await getAuthOrchestrator().checkAuth();
            const authState = getAuthOrchestrator().getState();
            const me = {
                ok: true,
                status: 200,
                h: {},
                body: {
                    is_authenticated: authState.is_authenticated,
                    session_ready: authState.session_ready,
                    user_id: authState.user_id,
                    source: authState.source,
                }
            };

            const diag = await apiFetch('/v1/_diag/auth', { auth: true })
                .then(r => r.json()).catch(e => ({ error: String(e) }));

            // Also load backend echo endpoints for visibility
            const [hdrs, cookies] = await Promise.all([
                apiFetch('/v1/debug/headers', { auth: false }).then(r => r.json()).catch(() => null),
                apiFetch('/v1/debug/cookies', { auth: false }).then(r => r.json()).catch(() => null),
            ]);

            setR({ me, diag, headers: hdrs, cookies, method: 'orchestrator' });
        })();
    }, []);

    const handleDirectWhoami = async () => {
        // DANGER: Direct /v1/whoami call - only on explicit button click
        console.warn('🚨 DEBUG: Using direct /v1/whoami bypass (manual trigger)');
        const me = await apiFetch('/v1/whoami', {
            method: 'GET',
            headers: {
                'X-Auth-Orchestrator': 'debug-bypass'
            }
        })
            .then(r => ({ ok: r.ok, status: r.status, h: Object.fromEntries(r.headers), body: r.json().catch(() => null) }))
            .catch(e => ({ error: String(e) }));

        setR((prev: any) => ({ ...prev, directWhoami: me, method: 'direct' }));
    };

    return (
        <div className="p-6">
            <div className="mb-4">
                <p className="text-sm text-green-600 font-semibold mb-2">
                    ✅ Using AuthOrchestrator (recommended)
                </p>
                <button
                    onClick={handleDirectWhoami}
                    className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm font-semibold"
                >
                    🚨 Direct WhoAmI (Danger)
                </button>
                <p className="text-xs text-gray-600 mt-1">
                    Only click this for debugging. It bypasses the orchestrator contract.
                </p>
            </div>
            <pre className="text-xs overflow-auto bg-gray-100 p-4 rounded">
                {JSON.stringify(r, null, 2)}
            </pre>
        </div>
    );
}
