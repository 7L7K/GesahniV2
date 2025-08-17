'use client';

import { useState, useEffect } from 'react';
import { getBootstrapManager, type BootstrapState, type BootstrapManager } from '@/services/bootstrapManager';

/**
 * Hook to access the current bootstrap state
 * This is the preferred way for React components to read bootstrap state
 */
export function useBootstrapState(): BootstrapState {
    const [state, setState] = useState<BootstrapState>(() => getBootstrapManager().getState());

    useEffect(() => {
        const unsubscribe = getBootstrapManager().subscribe(setState);
        return unsubscribe;
    }, []);

    return state;
}

/**
 * Hook to access the Bootstrap Manager instance
 * Use this when you need to trigger bootstrap actions
 */
export function useBootstrapManager(): BootstrapManager {
    return getBootstrapManager();
}

/**
 * Convenience hook that returns both state and manager
 */
export function useBootstrap(): { state: BootstrapState; manager: BootstrapManager } {
    const state = useBootstrapState();
    const manager = useBootstrapManager();

    return { state, manager };
}
