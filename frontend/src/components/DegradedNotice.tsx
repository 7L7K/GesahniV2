'use client';

import React from 'react';
import { useBackendStatus } from '@/hooks/useBackendStatus';

export default function DegradedNotice() {
    const { deps } = useBackendStatus();
    if (!deps || deps.status !== 'degraded') return null;
    const failing = Object.entries(deps.checks)
        .filter(([k, v]) => k !== 'backend' && v === 'error')
        .map(([k]) => k);
    if (failing.length === 0) return null;
    const tooltip = `${failing.join(', ')} down`;
    return (
        <div className="mx-auto max-w-3xl px-4 py-1 text-[12px] bg-amber-100 text-amber-900 dark:bg-amber-900/30 dark:text-amber-100">
            <span title={tooltip}>⚠︎ Some services degraded: {failing.join(', ')}</span>
        </div>
    );
}
