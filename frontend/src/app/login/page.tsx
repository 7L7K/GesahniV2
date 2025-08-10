'use client';

import { Suspense, useEffect, useState } from 'react';
import { login, register, setTokens, apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { useRouter, useSearchParams } from 'next/navigation';

function LoginPageInner() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [mode, setMode] = useState<'login' | 'register'>('login');
    const [error, setError] = useState<string>('');
    const [loading, setLoading] = useState(false);
    const router = useRouter();
    const params = useSearchParams();
    const next = params.get('next') || '/';

    // Handle Google OAuth redirect carrying tokens in query
    useEffect(() => {
        const access = params.get('access_token');
        const refresh = params.get('refresh_token') || undefined;
        if (access) {
            setTokens(access, refresh);
            document.cookie = `auth:hint=1; path=/; max-age=${14 * 24 * 60 * 60}`;
            router.replace(next);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const submit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        try {
            if (mode === 'login') {
                await login(username, password);
            } else {
                await register(username, password);
                await login(username, password);
            }
            document.cookie = `auth:hint=1; path=/; max-age=${14 * 24 * 60 * 60}`;
            router.replace(next);
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            setLoading(false);
        }
    };

    return (
        <main className="mx-auto max-w-md px-4 py-10">
            <div className="rounded-xl border bg-card p-6 shadow">
                <h1 className="mb-6 text-xl font-semibold">{mode === 'login' ? 'Sign in' : 'Create account'}</h1>
                <form onSubmit={submit} className="space-y-4">
                    <div>
                        <label htmlFor="username" className="mb-1 block text-sm">Username</label>
                        <input
                            id="username"
                            className="w-full rounded border px-3 py-2"
                            value={username}
                            onChange={e => setUsername(e.target.value)}
                            required
                            autoComplete="username"
                        />
                    </div>
                    <div>
                        <label htmlFor="password" className="mb-1 block text-sm">Password</label>
                        <input
                            id="password"
                            type="password"
                            className="w-full rounded border px-3 py-2"
                            value={password}
                            onChange={e => setPassword(e.target.value)}
                            required
                            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                        />
                    </div>
                    {error && <p className="text-sm text-red-600">{error}</p>}
                    <Button type="submit" disabled={loading} className="w-full">
                        {loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
                    </Button>
                </form>
                <div className="my-4 text-center text-xs text-muted-foreground">or</div>
                <Button
                    variant="outline"
                    className="w-full"
                    type="button"
                    onClick={async () => {
                        try {
                            const res = await apiFetch(`/v1/google/auth/login_url?next=${encodeURIComponent(next)}`, { auth: false });
                            if (!res.ok) throw new Error('Failed to start Google login');
                            const { auth_url } = await res.json();
                            window.location.href = auth_url;
                        } catch (err) {
                            setError(err instanceof Error ? err.message : String(err));
                        }
                    }}
                >
                    Continue with Google
                </Button>
                <div className="mt-4 text-center text-sm">
                    {mode === 'login' ? (
                        <button className="underline" onClick={() => setMode('register')}>Need an account? Register</button>
                    ) : (
                        <button className="underline" onClick={() => setMode('login')}>Already have an account? Sign in</button>
                    )}
                </div>
            </div>
        </main>
    );
}

export default function LoginPage() {
    return (
        <Suspense fallback={<main className="mx-auto max-w-md px-4 py-10"><div className="text-sm text-muted-foreground">Loading…</div></main>}>
            <LoginPageInner />
        </Suspense>
    );
}


