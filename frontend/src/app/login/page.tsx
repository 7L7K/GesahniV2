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
            const uname = username.trim().toLowerCase();
            if (!/^[a-z0-9_.-]{3,64}$/.test(uname)) {
                throw new Error('Invalid username. Use 3-64 chars: a-z, 0-9, _, ., -');
            }
            if (password.trim().length < 6) {
                throw new Error('Password too short');
            }
            if (mode === 'login') {
                await login(uname, password);
            } else {
                await register(uname, password);
                await login(uname, password);
            }
            document.cookie = `auth:hint=1; path=/; max-age=${14 * 24 * 60 * 60}`;
            router.replace(next);
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            // Normalize common backend errors for nicer UX
            if (/invalid_username/i.test(msg)) {
                setError('Invalid username. Use 3–64 chars: a-z, 0-9, _, ., -');
            } else if (/weak_password/i.test(msg)) {
                setError('Password is too weak. Use at least 8 characters with letters and numbers.');
            } else if (/username_taken/i.test(msg)) {
                setError('That username is already taken.');
            } else if (/invalid credentials/i.test(msg)) {
                setError('Incorrect username or password.');
            } else if (/rate_limited/i.test(msg)) {
                setError('Too many attempts. Please wait and try again.');
            } else {
                setError(msg);
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <main className="mx-auto max-w-md px-4 py-10">
            <div className="rounded-2xl border bg-card p-6 shadow-sm">
                <h1 className="mb-6 text-xl font-semibold">{mode === 'login' ? 'Sign in' : 'Create account'}</h1>
                <form onSubmit={submit} className="space-y-4">
                    <div>
                        <label htmlFor="username" className="mb-1 block text-sm">Username</label>
                        <input
                            id="username"
                            className="w-full rounded-md border px-3 py-2"
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
                            className="w-full rounded-md border px-3 py-2"
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
                            const msg = err instanceof Error ? err.message : String(err);
                            setError(msg || 'Google sign-in is temporarily unavailable.');
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


