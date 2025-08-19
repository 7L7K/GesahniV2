'use client';

import { Suspense, useEffect, useState } from 'react';
import { setTokens, apiFetch, bumpAuthEpoch } from '@/lib/api';
import { sanitizeNextPath } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { useRouter, useSearchParams } from 'next/navigation';
import { getAuthOrchestrator } from '@/services/authOrchestrator';
import GoogleSignInButton from '@/components/GoogleSignInButton';

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
            console.info('LOGIN oauth.tokens_in_query', {
                hasAccessToken: !!access,
                hasRefreshToken: !!refresh,
                accessTokenLength: access?.length || 0,
                refreshTokenLength: refresh?.length || 0,
                timestamp: new Date().toISOString(),
            });

            // Persist tokens in header mode
            setTokens(access, refresh);

            // Trigger Auth Orchestrator refresh after successful login
            const authOrchestrator = getAuthOrchestrator();
            console.info('LOGIN oauth.orchestrator.refresh.start', {
                timestamp: new Date().toISOString(),
            });

            authOrchestrator.refreshAuth().finally(() => {
                console.info('LOGIN oauth.orchestrator.refresh.complete', {
                    timestamp: new Date().toISOString(),
                });
                router.replace(next);
            });
        }
    }, [params, next, router]);

    // Handle OAuth errors from URL params
    useEffect(() => {
        const error = params.get('error');
        const errorDescription = params.get('error_description');

        if (error) {
            console.error('LOGIN oauth.error', {
                error,
                errorDescription,
                timestamp: new Date().toISOString(),
            });
            setError(errorDescription || `OAuth error: ${error}`);
        }
    }, [params]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        console.info('LOGIN submit.start', {
            mode,
            username: username ? `${username.substring(0, 3)}***` : 'empty',
            hasPassword: !!password,
            next,
            timestamp: new Date().toISOString(),
        });

        try {
            const endpoint = mode === 'login' ? '/v1/login' : '/v1/register';
            console.info('LOGIN api.request', {
                endpoint,
                method: 'POST',
                mode,
                timestamp: new Date().toISOString(),
            });

            const response = await apiFetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
                auth: false,
            });

            console.info('LOGIN api.response', {
                status: response.status,
                statusText: response.statusText,
                ok: response.ok,
                headers: Object.fromEntries(response.headers.entries()),
                timestamp: new Date().toISOString(),
            });

            if (response.ok) {
                const data = await response.json();
                console.info('LOGIN api.success', {
                    hasAccessToken: !!data.access_token,
                    hasRefreshToken: !!data.refresh_token,
                    accessTokenLength: data.access_token?.length || 0,
                    refreshTokenLength: data.refresh_token?.length || 0,
                    timestamp: new Date().toISOString(),
                });

                setTokens(data.access_token, data.refresh_token);
                bumpAuthEpoch();

                console.info('LOGIN tokens.set', {
                    authEpochBumped: true,
                    timestamp: new Date().toISOString(),
                });

                // Trigger Auth Orchestrator refresh after successful login
                const authOrchestrator = getAuthOrchestrator();
                console.info('LOGIN orchestrator.refresh.start', {
                    timestamp: new Date().toISOString(),
                });

                await authOrchestrator.refreshAuth();

                console.info('LOGIN orchestrator.refresh.complete', {
                    timestamp: new Date().toISOString(),
                });

                console.info('LOGIN navigation.start', {
                    next,
                    timestamp: new Date().toISOString(),
                });

                router.replace(next);

                console.info('LOGIN complete.success', {
                    timestamp: new Date().toISOString(),
                });
            } else {
                const errorData = await response.json().catch(() => ({}));
                console.error('LOGIN api.error', {
                    status: response.status,
                    statusText: response.statusText,
                    errorDetail: errorData.detail,
                    errorData,
                    timestamp: new Date().toISOString(),
                });
                setError(errorData.detail || `Failed to ${mode}`);
            }
        } catch (err) {
            console.error('LOGIN exception', {
                error: err instanceof Error ? err.message : String(err),
                errorType: err instanceof Error ? err.constructor.name : typeof err,
                stack: err instanceof Error ? err.stack : undefined,
                timestamp: new Date().toISOString(),
            });
            setError(err instanceof Error ? err.message : `Failed to ${mode}`);
        } finally {
            setLoading(false);
            console.info('LOGIN submit.end', {
                mode,
                timestamp: new Date().toISOString(),
            });
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

                <div className="space-y-6">
                    {/* Google Sign-in Button */}
                    <GoogleSignInButton next={next} disabled={loading} />

                    {/* Divider */}
                    <div className="relative">
                        <div className="absolute inset-0 flex items-center">
                            <div className="w-full border-t border-gray-300 dark:border-gray-600" />
                        </div>
                        <div className="relative flex justify-center text-sm">
                            <span className="px-2 bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400">
                                Or continue with email
                            </span>
                        </div>
                    </div>

                    {/* Email/Password Form */}
                    <form className="space-y-6" onSubmit={handleSubmit}>
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


