'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import ThemeToggle from '@/components/ThemeToggle';
import { Button } from '@/components/ui/button';
import { getToken, clearTokens, getBudget } from '@/lib/api';
import { usePathname, useRouter } from 'next/navigation';

export default function Header() {
    const [authed, setAuthed] = useState(false);
    const router = useRouter();
    const pathname = usePathname();

    useEffect(() => {
        setAuthed(Boolean(getToken()))
    }, [pathname])

    const doLogout = async () => {
        try { clearTokens() } finally {
            setAuthed(false)
            document.cookie = 'auth:hint=0; path=/; max-age=300'
            router.push('/')
        }
    }

    const [localMode, setLocalMode] = useState(false);
    const [nearCap, setNearCap] = useState(false);
    useEffect(() => {
        // Heuristic: server can set a cookie X-Local-Mode=1 via a middleware in offline mode.
        if (typeof document !== 'undefined') {
            setLocalMode(/X-Local-Mode=1/.test(document.cookie));
        }
        // Fetch budget hint for banner
        getBudget().then(b => setNearCap(Boolean(b.near_cap))).catch(() => setNearCap(false));
    }, [pathname]);

    return (
        <header className="sticky top-0 z-30 border-b bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
            <div className="mx-auto max-w-3xl px-4 h-14 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <div className="h-6 w-6 rounded bg-primary" />
                    <Link href="/" className="font-semibold tracking-tight">Gesahni</Link>
                    {localMode && (
                        <span className="ml-2 text-[10px] uppercase tracking-wide rounded px-1.5 py-0.5 bg-yellow-500/20 text-yellow-900 dark:text-yellow-200">
                            Local mode
                        </span>
                    )}
                </div>
                <nav className="flex items-center gap-3 text-sm text-muted-foreground">
                    <Link href="/tv" className="hover:text-foreground">TV</Link>
                    {authed && (
                        <>
                            <Link href="/capture" className="hover:text-foreground">Capture</Link>
                            <Link href="/settings" className="hover:text-foreground">Settings</Link>
                            <Link href="/admin" className="hover:text-foreground">Admin</Link>
                        </>
                    )}
                    {!authed ? (
                        <Link href={`/login?next=${encodeURIComponent(pathname || '/')}`} className="hover:text-foreground">Login</Link>
                    ) : (
                        <Button size="sm" variant="ghost" onClick={doLogout}>Logout</Button>
                    )}
                    <ThemeToggle />
                </nav>
            </div>
            {nearCap && (
                <div className="mx-auto max-w-3xl px-4 py-1 text-[12px] bg-amber-100 text-amber-900 dark:bg-amber-900/30 dark:text-amber-100">
                    You’re nearing your daily budget. Responses may be shorter or use LLaMA.
                </div>
            )}
        </header>
    );
}


