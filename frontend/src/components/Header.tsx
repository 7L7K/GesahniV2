'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import ThemeToggle from '@/components/ThemeToggle';
// Clerk removed - using cookie authentication only
import { useAuthState } from '@/hooks/useAuth';
import { getBudget } from '@/lib/api';
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

    // Debug: Track Header re-renders to verify reactive auth state updates
    console.info('🎨 HEADER_RENDER:', {
        authed,
        source: authState.source,
        userId: authState.user_id,
        sessionReady: authState.session_ready,
        pathname,
        timestamp: new Date().toISOString(),
    });

    // Debug: Track when auth state actually changes
    useEffect(() => {
        console.info('🔄 HEADER_AUTH_STATE_CHANGED:', {
            is_authenticated: authState.is_authenticated,
            session_ready: authState.session_ready,
            source: authState.source,
            user_id: authState.user_id,
            whoamiOk: authState.whoamiOk,
            version: authState.version,
            timestamp: new Date().toISOString(),
        });
    }, [authState.is_authenticated, authState.session_ready, authState.source, authState.user_id, authState.whoamiOk, authState.version]);

    // Debug logging for auth state
    console.log('🔍 HEADER_AUTH_DEBUG:', {
        is_authenticated: authState.is_authenticated,
        session_ready: authState.session_ready,
        user_id: authState.user_id,
        source: authState.source,
        whoamiOk: authState.whoamiOk,
        timestamp: new Date().toISOString()
    });

    // Cookie mode only - show auth buttons if not authenticated
    const _shouldShowAuthButtons = !authed;

    const doLogout = () => {
        console.info('🚪 HEADER_LOGOUT: Navigating to logout flow');
        router.replace('/logout');
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
                        <ClientOnly>
                            {authState.demo && (
                                <div className="flex items-center gap-1 text-xs text-purple-600">
                                    <div className="w-2 h-2 bg-purple-500 rounded-full"></div>
                                    Demo Mode
                                </div>
                            )}
                        </ClientOnly>
                    </nav>
                </div>
            </div>
        </header>
    );
}
