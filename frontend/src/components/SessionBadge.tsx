'use client';

import React from 'react';
import { useAuthState } from '@/hooks/useAuth';

export default function SessionBadge() {
    const s = useAuthState();
    const authed = s?.is_authenticated;
    const ready = s?.session_ready;
    const userId = s?.user_id;

    const bg = !authed ? 'bg-rose-600' : (ready ? 'bg-emerald-600' : 'bg-yellow-600');
    const label = !authed ? 'auth:none' : (userId ? `auth:${String(userId).slice(0, 6)}` : 'auth:pending');

    return (
        <div className={`px-2 py-0.5 rounded text-xs text-white ${bg}`} title={`is_authenticated=${String(authed)} session_ready=${String(ready)} user_id=${userId || 'null'}`} data-testid="session-badge">
            {label}
        </div>
    );
}


