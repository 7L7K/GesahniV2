'use client';

import { useEffect, ReactNode } from 'react';
import { getAuthOrchestrator } from '@/services/authOrchestrator';

interface AuthProviderProps {
    children: ReactNode;
}

/**
 * Auth Provider - Initializes the Auth Orchestrator on app mount
 * 
 * This component should be placed at the root of the app to ensure
 * the Auth Orchestrator is initialized once and manages all auth state.
 */
export default function AuthProvider({ children }: AuthProviderProps) {
    useEffect(() => {
        // Initialize the Auth Orchestrator on mount
        const orchestrator = getAuthOrchestrator();

        const initAuth = async () => {
            try {
                await orchestrator.initialize();
            } catch (error) {
                console.error('Failed to initialize Auth Orchestrator:', error);
            }
        };

        initAuth();

        // Cleanup on unmount
        return () => {
            orchestrator.cleanup();
        };
    }, []);

    return <>{children}</>;
}
