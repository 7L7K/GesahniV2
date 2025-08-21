'use client';

import { useEffect } from 'react';
// Clerk integration disabled for cookie-mode frontend; leave component as passthrough

// Custom hook to manage Clerk token integration
function useClerkTokenIntegration() {
    useEffect(() => {
        const updateClerkToken = async () => {
            try {
                // Check if Clerk is available
                if (typeof window !== 'undefined' && window.Clerk) {
                    const token = await window.Clerk.session?.getToken();
                    if (token) {
                        // Set the token on window for the getToken function to access
                        (window as any).__clerkToken = token;
                        console.debug('CLERK_TOKEN_INTEGRATION: Token set', {
                            hasToken: !!token,
                            tokenLength: token?.length || 0,
                            timestamp: new Date().toISOString(),
                        });
                    } else {
                        // Clear the token if no session
                        delete (window as any).__clerkToken;
                        console.debug('CLERK_TOKEN_INTEGRATION: Token cleared', {
                            timestamp: new Date().toISOString(),
                        });
                    }
                }
            } catch (error) {
                console.debug('CLERK_TOKEN_INTEGRATION: Error updating token', {
                    error: error instanceof Error ? error.message : String(error),
                    timestamp: new Date().toISOString(),
                });
            }
        };

        // Update token immediately
        updateClerkToken();

        // Set up listener for Clerk session changes
        if (typeof window !== 'undefined' && window.Clerk) {
            window.Clerk.addListener(({ user, session }) => {
                updateClerkToken();
            });
        }

        // Cleanup
        return () => {
            if (typeof window !== 'undefined' && window.Clerk) {
                window.Clerk.removeListener(({ user, session }) => {
                    updateClerkToken();
                });
            }
        };
    }, []);
}

export default function AuthProvider({ children }: { children: React.ReactNode }) {
    // No Clerk: simply render children
    return <>{children}</>;
}
