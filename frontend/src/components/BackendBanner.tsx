'use client';

import React from 'react';
import { useBackendStatus } from '@/hooks/useBackendStatus';

export default function BackendBanner() {
    const { ready } = useBackendStatus();
    if (ready === 'online') return null;
    return (
        <div className="mx-auto max-w-3xl px-4 py-1 text-[12px] bg-red-100 text-red-900 dark:bg-red-900/30 dark:text-red-100">
            Backend offline — retrying…
        </div>
    );
}


