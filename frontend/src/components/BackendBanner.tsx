'use client';

import React from 'react';
import { useBackendStatus } from '@/hooks/useBackendStatus';

export default function BackendBanner() {
    const { ready, hasChecked } = useBackendStatus();

    // Only show banner if we've checked and found the backend to be offline
    if (!hasChecked || ready === 'online') return null;

    return (
        <div className="mx-auto max-w-3xl px-4 py-1 text-[12px] bg-red-100 text-red-900 dark:bg-red-900/30 dark:text-red-100">
            Backend offline — retrying…
        </div>
    );
}
