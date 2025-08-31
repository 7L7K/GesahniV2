import { useEffect, useState } from 'react';
import { listenForAuthErrors, getAuthErrorMessage, type AuthErrorEvent } from '@/lib/api';

/**
 * Hook to handle authentication errors with user-friendly UI feedback
 *
 * Usage:
 * ```tsx
 * const { error, dismissError } = useAuthErrorHandler();
 *
 * if (error) {
 *   return (
 *     <Toast message={error.title} description={error.message} onClose={dismissError}>
 *       {error.action && (
 *         <Button as={Link} href={error.action.href}>
 *           {error.action.label}
 *         </Button>
 *       )}
 *     </Toast>
 *   );
 * }
 * ```
 */
export function useAuthErrorHandler() {
    const [currentError, setCurrentError] = useState<ReturnType<typeof getAuthErrorMessage> | null>(null);

    useEffect(() => {
        // Listen for auth errors and format them for UI display
        const unsubscribe = listenForAuthErrors((error: AuthErrorEvent) => {
            const formattedError = getAuthErrorMessage(error);
            setCurrentError(formattedError);
        });

        return unsubscribe;
    }, []);

    const dismissError = () => {
        setCurrentError(null);
    };

    return {
        error: currentError,
        dismissError,
        hasError: currentError !== null
    };
}

/**
 * Hook for more granular error handling with custom callbacks
 *
 * Usage:
 * ```tsx
 * useAuthErrorListener({
 *   onSpotifyRequired: () => navigate('/spotify/connect'),
 *   onAuthRequired: () => navigate('/login'),
 *   onPermissionDenied: (error) => showModal(error.message)
 * });
 * ```
 */
export function useAuthErrorListener(callbacks: {
    onSpotifyRequired?: (error: AuthErrorEvent) => void;
    onAuthRequired?: (error: AuthErrorEvent) => void;
    onPermissionDenied?: (error: AuthErrorEvent) => void;
    onAnyError?: (error: AuthErrorEvent) => void;
}) {
    useEffect(() => {
        const unsubscribe = listenForAuthErrors((error: AuthErrorEvent) => {
            // Call specific callback if provided
            switch (error.type) {
                case 'spotify_connection_required':
                    callbacks.onSpotifyRequired?.(error);
                    break;
                case 'authentication_required':
                    callbacks.onAuthRequired?.(error);
                    break;
                case 'permission_denied':
                    callbacks.onPermissionDenied?.(error);
                    break;
            }

            // Always call general callback if provided
            callbacks.onAnyError?.(error);
        });

        return unsubscribe;
    }, [callbacks]);
}
