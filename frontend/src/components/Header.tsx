'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import ThemeToggle from '@/components/ThemeToggle';
import { SignedIn, SignInButton, SignUpButton, UserButton, useAuth } from '@clerk/nextjs';
import { useAuthState } from '@/hooks/useAuth';
import { getToken, clearTokens, getBudget, bumpAuthEpoch, apiFetch } from '@/lib/api';
import ClientOnly from './ClientOnly';

export default function Header() {
    const authState = useAuthState();
    const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
    const router = useRouter();
    const pathname = usePathname();
    // Note: useAuth() must only be used within ClerkProvider.
    // We render a small child component inside <SignedIn> to bump auth epoch on user changes.
    const { isSignedIn, isLoaded } = useAuth();

    // Use centralized auth state instead of making direct whoami calls
    const authed = authState.isAuthenticated;

    // For Clerk mode, we need to check both Clerk's state and backend state
    // Only show auth buttons if Clerk is loaded and user is not signed in
    const shouldShowAuthButtons = clerkEnabled ? (isLoaded && !isSignedIn) : !authed;

    const doLogout = async () => {
        // Clear tokens and state immediately for better UX
        try { clearTokens() } catch { /* ignore */ }
        try { document.cookie = 'auth_hint=0; path=/; max-age=300' } catch { /* ignore */ }

        // Navigate immediately
        router.push('/')

        // Fire-and-forget backend logout
        try {
            await apiFetch('/v1/auth/logout', { method: 'POST' })
        } catch {
            /* ignore - user already navigated away */
        }
    }

    const [localMode, setLocalMode] = useState(false);
    const [nearCap, setNearCap] = useState(false);

    // Budget check (only when authenticated)
    useEffect(() => {
        if (!authed) return;
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
    }, [authed]);

    // Local mode detection
    useEffect(() => {
        const checkLocalMode = () => {
            try {
                if (typeof window !== 'undefined' && window.location) {
                    const isLocal = window.location.hostname === '127.0.0.1' ||
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
                    </nav>
                </div>
                <div className="flex flex-1 items-center justify-between space-x-2 md:justify-end">
                    <div className="w-full flex-1 md:w-auto md:flex-none">
                    </div>
                    <nav className="flex items-center space-x-2">
                        {clerkEnabled ? (
                            <>
                                {!isLoaded ? (
                                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary"></div>
                                ) : shouldShowAuthButtons ? (
                                    <>
                                        <SignInButton mode="modal">
                                            <Button variant="ghost" size="sm">
                                                Sign In
                                            </Button>
                                        </SignInButton>
                                        <SignUpButton mode="modal">
                                            <Button size="sm">
                                                Sign Up
                                            </Button>
                                        </SignUpButton>
                                    </>
                                ) : (
                                    <SignedIn>
                                        <UserButton afterSignOutUrl="/" />
                                    </SignedIn>
                                )}
                            </>
                        ) : (
                            <>
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
                            </>
                        )}
                        <ThemeToggle />
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

