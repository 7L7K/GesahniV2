'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import ThemeToggle from '@/components/ThemeToggle';
// Clerk removed - using cookie authentication only
import { useAuthState } from '@/hooks/useAuth';
import { getToken, clearTokens, getBudget, bumpAuthEpoch, apiFetch } from '@/lib/api';
import { getAuthOrchestrator } from '@/services/authOrchestrator';
import ClientOnly from './ClientOnly';
import SessionBadge from '@/components/SessionBadge';

// Clerk completely removed - using cookie authentication only

export default function Header() {
    const authState = useAuthState();
    const router = useRouter();
    const pathname = usePathname();
    // Note: useAuth() must only be used within ClerkProvider.
    // We render a small child component inside <SignedIn> to bump auth epoch on user changes.
    // Clerk removed - using only cookie auth state

    // Use centralized auth state instead of making direct whoami calls
    const authed = authState.is_authenticated;

    // Cookie mode only - show auth buttons if not authenticated
    const shouldShowAuthButtons = !authed;

    const doLogout = async () => {
        // Clear tokens and state immediately for better UX
        try {
            clearTokens()
            console.info('LOGOUT: Tokens cleared');
        } catch (error) {
            console.error('LOGOUT: Error clearing tokens:', error);
        }

        // Trigger auth refresh to update state
        try {
            const authOrchestrator = getAuthOrchestrator();
            await authOrchestrator.refreshAuth();
            console.info('LOGOUT: Auth state refreshed');
        } catch (error) {
            console.error('LOGOUT: Error refreshing auth state:', error);
        }

        // Navigate immediately with logout parameter to prevent token recreation
        router.push('/login?logout=true')

        // Fire-and-forget backend logout
        try {
            await apiFetch('/v1/auth/logout', { method: 'POST' })
        } catch {
            /* ignore - user already navigated away */
        }
    }

    const [localMode, setLocalMode] = useState(false);
    const [nearCap, setNearCap] = useState(false);

    // Budget check (only when authenticated and session is ready)
    useEffect(() => {
        if (!(authed && authState.session_ready)) return;
        let cancelled = false;
        const checkBudget = async () => {
            try {
                const budget = await getBudget();
                if (!cancelled) {
                    setNearCap(budget.near_cap || false);
                }
            } catch {
                if (!cancelled) setNearCap(false);
            }
        };
        checkBudget();
        return () => { cancelled = true };
    }, [authed, authState.session_ready]);

    // Local mode detection
    useEffect(() => {
        const checkLocalMode = () => {
            try {
                if (typeof window !== 'undefined' && window.location) {
                    const isLocal = window.location.hostname === 'localhost' ||
                        window.location.hostname === 'localhost' ||
                        window.location.hostname.includes('.local');
                    setLocalMode(isLocal);
                } else {
                    setLocalMode(false);
                }
            } catch {
                setLocalMode(false);
            }
        };
        checkLocalMode();
    }, []);

    return (
        <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
            <div className="container flex h-14 items-center">
                <div className="mr-4 hidden md:flex">
                    <Link href="/" className="mr-6 flex items-center space-x-2">
                        <span className="hidden font-bold sm:inline-block">
                            Gesahni
                        </span>
                    </Link>
                    <nav className="flex items-center space-x-6 text-sm font-medium">
                        <Link
                            href="/"
                            className={`transition-colors hover:text-foreground/80 ${pathname === "/" ? "text-foreground" : "text-foreground/60"
                                }`}
                        >
                            Chat
                        </Link>
                        <Link
                            href="/capture"
                            className={`transition-colors hover:text-foreground/80 ${pathname === "/capture" ? "text-foreground" : "text-foreground/60"
                                }`}
                        >
                            Capture
                        </Link>
                        <Link
                            href="/tv"
                            className={`transition-colors hover:text-foreground/80 ${pathname === "/tv" ? "text-foreground" : "text-foreground/60"
                                }`}
                        >
                            TV
                        </Link>
                        <Link
                            href="/settings"
                            className={`transition-colors hover:text-foreground/80 ${pathname === "/settings" ? "text-foreground" : "text-foreground/60"
                                }`}
                        >
                            Settings
                        </Link>
                        <Link
                            href="/admin"
                            className={`transition-colors hover:text-foreground/80 ${pathname === "/admin" ? "text-foreground" : "text-foreground/60"
                                }`}
                        >
                            Admin
                        </Link>
                        <Link
                            href="/debug"
                            className={`transition-colors hover:text-foreground/80 ${pathname === "/debug" ? "text-foreground" : "text-foreground/60"
                                }`}
                        >
                            Debug
                        </Link>
                    </nav>
                </div>
                <div className="flex flex-1 items-center justify-between space-x-2 md:justify-end">
                    <div className="w-full flex-1 md:w-auto md:flex-none">
                    </div>
                    <nav className="flex items-center space-x-2">
                        {/* Cookie authentication only */}
                        {authed ? (
                            <Button variant="ghost" size="sm" onClick={doLogout}>
                                Logout
                            </Button>
                        ) : (
                            <Link href="/login">
                                <Button variant="ghost" size="sm">
                                    Login
                                </Button>
                            </Link>
                        )}
                        <ThemeToggle />
                        <ClientOnly>
                            <SessionBadge />
                        </ClientOnly>
                        <ClientOnly>
                            {localMode && (
                                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                                    <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                                    Local
                                </div>
                            )}
                        </ClientOnly>
                        <ClientOnly>
                            {nearCap && (
                                <div className="flex items-center gap-1 text-xs text-orange-600">
                                    <div className="w-2 h-2 bg-orange-500 rounded-full"></div>
                                    Near Cap
                                </div>
                            )}
                        </ClientOnly>
                    </nav>
                </div>
            </div>
        </header>
    );
}
