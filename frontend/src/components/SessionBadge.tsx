'use client';

import React, { useEffect } from 'react';
import { useAuthState } from '@/hooks/useAuth';

export default function SessionBadge() {
    const s = useAuthState();
    const authed = s?.is_authenticated;
    const ready = s?.session_ready;
    const userId = s?.user_id;

    // Debug: Track SessionBadge re-renders to verify reactive auth state updates
    console.info('🎨 SESSION_BADGE_RENDER:', {
        authed,
        ready,
        userId,
        source: s?.source,
        timestamp: new Date().toISOString(),
    });

    // Debug: Track when auth state actually changes
    useEffect(() => {
        console.info('🔄 SESSION_BADGE_STATE_CHANGED:', {
            is_authenticated: s?.is_authenticated,
            session_ready: s?.session_ready,
            source: s?.source,
            user_id: s?.user_id,
            whoamiOk: s?.whoamiOk,
            version: s?.version,
            timestamp: new Date().toISOString(),
        });
    }, [s?.is_authenticated, s?.session_ready, s?.source, s?.user_id, s?.whoamiOk, s?.version]);

    const bg = !authed ? 'bg-rose-600' : (ready ? 'bg-emerald-600' : 'bg-yellow-600');
    const demo = s?.demo;
    const label = !authed ? 'auth:none' : (userId ? `auth:${String(userId).slice(0, 6)}${demo ? '(demo)' : ''}` : 'auth:pending');

    return (
        <div className={`px-2 py-0.5 rounded text-xs text-white ${bg}`} title={`is_authenticated=${String(authed)} session_ready=${String(ready)} user_id=${userId || 'null'}`} data-testid="session-badge">
            {label}
        </div>
    );
}
