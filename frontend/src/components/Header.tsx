'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import ThemeToggle from '@/components/ThemeToggle';
import { Button } from '@/components/ui/button';
import { isAuthed, logout } from '@/lib/api';
import { usePathname, useRouter } from 'next/navigation';

export default function Header() {
    const [authed, setAuthed] = useState(false);
    const router = useRouter();
    const pathname = usePathname();

    useEffect(() => {
        setAuthed(isAuthed());
    }, [pathname]);

    const doLogout = async () => {
        await logout();
        setAuthed(false);
        // Hint server components that we are logged out
        document.cookie = 'auth:hint=0; path=/; max-age=300';
        router.push('/');
    };

    const [localMode, setLocalMode] = useState(false);
    useEffect(() => {
        // Heuristic: server can set a cookie X-Local-Mode=1 via a middleware in offline mode.
        if (typeof document !== 'undefined') {
            setLocalMode(/X-Local-Mode=1/.test(document.cookie));
        }
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
                <div className="flex items-center gap-2">
                    {authed && (
                        <Link href="/capture" className="text-sm hover:underline">Capture</Link>
                    )}
                    {!authed ? (
                        <Link href={`/login?next=${encodeURIComponent(pathname || '/')}`} className="text-sm hover:underline">Login</Link>
                    ) : (
                        <Button size="sm" variant="ghost" onClick={doLogout}>Logout</Button>
                    )}
                    <ThemeToggle />
                </div>
            </div>
        </header>
    );
}


