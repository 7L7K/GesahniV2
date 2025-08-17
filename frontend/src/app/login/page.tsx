'use client';

import { Suspense, useEffect, useState } from 'react';
import { setTokens, apiFetch, bumpAuthEpoch } from '@/lib/api';
import { sanitizeNextPath } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { useRouter, useSearchParams } from 'next/navigation';
import { getAuthOrchestrator } from '@/services/authOrchestrator';

function LoginPageInner() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [mode, setMode] = useState<'login' | 'register'>('login');
    const [error, setError] = useState<string>('');
    const [loading, setLoading] = useState(false);
    const router = useRouter();
    const params = useSearchParams();
    const next = sanitizeNextPath(params.get('next'), '/');

    // Handle Google OAuth redirect carrying tokens in query
    useEffect(() => {
        const access = params.get('access_token');
        const refresh = params.get('refresh_token') || undefined;
        if (access) {
            // Persist in header mode for SPA; also ensure server cookies via refresh
            setTokens(access, refresh);
            document.cookie = `auth_hint=1; path=/; max-age=${14 * 24 * 60 * 60}`;
            // Fire-and-forget to backend to rotate/ensure HttpOnly cookies
            try { console.info('AUTH finisher.trigger reason=cookie.missing'); } catch { }
            {
                const headers: Record<string, string> = { 'X-Auth-Intent': 'refresh' };
                try {
                    const m = document.cookie.split('; ').find(c => c.startsWith('csrf_token='));
                    if (m) headers['X-CSRF-Token'] = decodeURIComponent(m.split('=')[1] || '');
                } catch { }
                apiFetch('/v1/auth/refresh', { method: 'POST', headers, auth: false }).finally(() => {
                    // Trigger Auth Orchestrator refresh after successful login
                    const authOrchestrator = getAuthOrchestrator();
                    authOrchestrator.refreshAuth().finally(() => {
                        router.replace(next);
                    });
                });
            }
        }
    }, [params, next, router]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            const endpoint = mode === 'login' ? '/v1/login' : '/v1/register';
            const response = await apiFetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
                auth: false,
            });

            if (response.ok) {
                const data = await response.json();
                setTokens(data.access_token, data.refresh_token);
                document.cookie = `auth_hint=1; path=/; max-age=${14 * 24 * 60 * 60}`;
                bumpAuthEpoch();

                // Trigger Auth Orchestrator refresh after successful login
                const authOrchestrator = getAuthOrchestrator();
                await authOrchestrator.refreshAuth();

                router.replace(next);
            } else {
                const errorData = await response.json().catch(() => ({}));
                setError(errorData.detail || `Failed to ${mode}`);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : `Failed to ${mode}`);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800">
            <div className="max-w-md w-full space-y-8 p-8 bg-white dark:bg-gray-800 rounded-xl shadow-lg">
                <div className="text-center">
                    <h2 className="text-3xl font-bold text-gray-900 dark:text-white">
                        {mode === 'login' ? 'Sign In' : 'Create Account'}
                    </h2>
                    <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                        {mode === 'login'
                            ? 'Welcome back to Gesahni'
                            : 'Join Gesahni to get started'
                        }
                    </p>
                </div>

                <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
                    <div className="space-y-4">
                        <div>
                            <label htmlFor="username" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                                Username
                            </label>
                            <input
                                id="username"
                                name="username"
                                type="text"
                                required
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                className="mt-1 block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white"
                                placeholder="Enter your username"
                            />
                        </div>
                        <div>
                            <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                                Password
                            </label>
                            <input
                                id="password"
                                name="password"
                                type="password"
                                required
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="mt-1 block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 dark:bg-gray-700 dark:text-white"
                                placeholder="Enter your password"
                            />
                        </div>
                    </div>

                    {error && (
                        <div className="text-red-600 dark:text-red-400 text-sm text-center">
                            {error}
                        </div>
                    )}

                    <div>
                        <Button
                            type="submit"
                            disabled={loading}
                            className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
                        >
                            {loading ? 'Processing...' : (mode === 'login' ? 'Sign In' : 'Create Account')}
                        </Button>
                    </div>

                    <div className="text-center">
                        <button
                            type="button"
                            onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
                            className="text-sm text-indigo-600 dark:text-indigo-400 hover:text-indigo-500"
                        >
                            {mode === 'login'
                                ? "Don't have an account? Sign up"
                                : "Already have an account? Sign in"
                            }
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

export default function LoginPage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
            </div>
        }>
            <LoginPageInner />
        </Suspense>
    );
}


