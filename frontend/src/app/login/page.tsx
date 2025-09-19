'use client';

import { Suspense, useEffect, useState } from 'react';
import { setTokens, apiFetch, bumpAuthEpoch } from '@/lib/api';
import { sanitizeNextPath, captureNextPathToBackend } from '@/lib/redirects';
import { safeNext } from '@/lib/redirect-utils';
import { Button } from '@/components/ui/button';
import { useRouter, useSearchParams } from 'next/navigation';
import { getAuthOrchestrator } from '@/services/authOrchestrator';
import { logAuth } from '@/auth/debug';
import GoogleSignInButton from '@/components/GoogleSignInButton';

function LoginPageInner() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [mode, setMode] = useState<'login' | 'register'>('login');
    const [error, setError] = useState<string>('');
    const [loading, setLoading] = useState(false);
    const [checkingAuth, setCheckingAuth] = useState(true);
    const router = useRouter();
    const params = useSearchParams();
    // sanitizeNextPath prevents open redirects by rejecting absolute/protocol-relative
    // URLs and auth paths that could cause redirect loops. This ensures users are only
    // redirected to safe, same-origin application pages after login completion.
    const next = sanitizeNextPath(params?.get('next') || null);

    // Check if user is already authenticated and redirect if so
    useEffect(() => {
        const checkExistingAuth = async () => {
            try {
                console.info('LOGIN auth.check.start', {
                    timestamp: new Date().toISOString(),
                });

                const authOrchestrator = getAuthOrchestrator();
                const authState = authOrchestrator.getState();

                // If already authenticated, redirect immediately
                if (authState.is_authenticated && authState.session_ready) {
                    console.info('LOGIN auth.check.already_authenticated', {
                        userId: authState.user_id,
                        source: authState.source,
                        timestamp: new Date().toISOString(),
                    });

                    // Use safeNext to prevent redirect loops
                    const redirectTo = safeNext(params?.get('next')) || '/';
                    console.info('LOGIN auth.check.redirect', {
                        redirectTo,
                        timestamp: new Date().toISOString(),
                    });
                    router.replace(redirectTo);
                    return;
                }

                // If not authenticated, trigger a fresh auth check
                console.info('LOGIN auth.check.trigger_refresh', {
                    timestamp: new Date().toISOString(),
                });
                await authOrchestrator.refreshAuth({ force: true });

                // Check again after refresh
                const refreshedState = authOrchestrator.getState();
                if (refreshedState.is_authenticated && refreshedState.session_ready) {
                    console.info('LOGIN auth.check.refresh_success', {
                        userId: refreshedState.user_id,
                        source: refreshedState.source,
                        timestamp: new Date().toISOString(),
                    });

                    const redirectTo = safeNext(params?.get('next')) || '/';
                    console.info('LOGIN auth.check.redirect_after_refresh', {
                        redirectTo,
                        timestamp: new Date().toISOString(),
                    });
                    router.replace(redirectTo);
                    return;
                }

                console.info('LOGIN auth.check.not_authenticated', {
                    timestamp: new Date().toISOString(),
                });

            } catch (error) {
                console.error('LOGIN auth.check.error', {
                    error: error instanceof Error ? error.message : String(error),
                    timestamp: new Date().toISOString(),
                });
            } finally {
                setCheckingAuth(false);
            }
        };

        checkExistingAuth();
    }, [router, params]);

    // Capture next parameter to backend gs_next cookie and normalize URL
    useEffect(() => {
        if (typeof window === 'undefined') return;

        // Read raw next directly from location.search to be resilient to Next's router updates
        const sp = new URLSearchParams(window.location.search);
        const rawNext = sp.get('next');

        // Capture next path to backend if present
        // sanitizeNextPath prevents open redirects by rejecting absolute/protocol-relative
        // URLs and auth paths that could cause redirect loops. This ensures users are only
        // redirected to safe, same-origin application pages after login completion.
        if (rawNext) {
            const sanitizedNext = sanitizeNextPath(rawNext);
            // Fire-and-forget POST to backend to set gs_next cookie
            captureNextPathToBackend(sanitizedNext);
        }

        if (!rawNext) return;

        // If sessionStorage indicates we've already normalized, skip.
        // Some browsers or extensions block sessionStorage; use URL flag fallback `sanitized=1`.
        try {
            if (window.sessionStorage && window.sessionStorage.getItem('sanitized_next_done')) return;
        } catch {
            // sessionStorage unavailable — fall through to URL-flag check below
        }

        // If URL already marked sanitized, skip normalization to avoid loops
        if (sp.get('sanitized') === '1') return;

        // Always clean the URL by removing next param and replacing with /login
        try {
            try { window.sessionStorage && window.sessionStorage.setItem('sanitized_next_done', '1'); } catch { }

            // Clean URL to /login by removing next query param
            if (window.history && window.history.replaceState) {
                const u = new URL(window.location.href);
                u.searchParams.delete('next');
                u.searchParams.set('sanitized', '1');
                const newUrl = u.pathname + u.search;
                if (window.location.pathname + window.location.search !== newUrl) {
                    window.history.replaceState(null, '', newUrl);
                }
            } else {
                router.replace('/login');
            }
            return;
        } catch (e) {
            console.warn('Failed to clean URL', e);
        }
    }, [router]);

    // Handle Google OAuth redirect carrying tokens in query
    useEffect(() => {
        const access = params?.get('access_token');
        const refresh = params?.get('refresh_token') || undefined;

        // Only set tokens if they're actually from OAuth (not from logout redirect)
        if (access && !params?.get('logout')) {
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

            authOrchestrator.refreshAuth({ force: true }).finally(() => {
                console.info('LOGIN oauth.orchestrator.refresh.complete', {
                    timestamp: new Date().toISOString(),
                });
                // Use safeNext to prevent redirect loops
                router.replace(safeNext(params?.get('next')) || '/');
                // Scrub OAuth query params from URL after successful auth
                try {
                    const url = new URL(window.location.href);
                    ['code', 'state', 'scope', 'authuser', 'prompt', 'hd', 'access_token', 'refresh_token'].forEach(p => url.searchParams.delete(p));
                    window.history.replaceState({}, document.title, url.toString());
                } catch (err) {
                    // ignore
                }
            });
        } else if (params?.get('logout')) {
            console.info('LOGIN logout_redirect: Skipping token setup due to logout parameter');
        }
    }, [params, next, router]);

    // Handle OAuth errors from URL params (only global auth errors, not Spotify-specific)
    useEffect(() => {
        if (!params) return;

        const error = params?.get('error');
        const errorDescription = params?.get('error_description');
        const spotifyError = params?.get('spotify_error');

        // Only handle global auth errors, not Spotify-specific errors
        // Spotify errors should be handled by the settings page with spotify_error param
        if (error && error !== 'spotify_oauth' && !spotifyError) {
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

        console.log('🔐 LOGIN: Starting login process...');
        console.log('🔐 LOGIN: Current cookies before login:', document.cookie);

        console.info('LOGIN submit.start', {
            mode,
            username: username ? `${username.substring(0, 3)}***` : 'empty',
            hasPassword: !!password,
            next,
            timestamp: new Date().toISOString(),
        });

        try {
            const isHeaderMode = process.env.NEXT_PUBLIC_HEADER_AUTH_MODE === '1';
            // Backend login expects username as a query param; registration accepts JSON body
            const endpoint = mode === 'login'
                ? `/v1/auth/login?username=${encodeURIComponent(username)}`
                : '/v1/auth/register';
            console.info('LOGIN api.request', {
                endpoint,
                method: 'POST',
                mode,
                timestamp: new Date().toISOString(),
            });

            console.log('🔐 FRONTEND_LOGIN_STEP_1: Making API call to:', endpoint);
            console.log('🔐 FRONTEND_LOGIN_STEP_2: Current cookies before login:', document.cookie);
            console.log('🔐 FRONTEND_LOGIN_STEP_3: Username being sent:', username);
            console.log('🔐 FRONTEND_LOGIN_STEP_4: Mode:', mode);

            const response = await apiFetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Auth-Orchestrator': 'legitimate'
                },
                // Include a body to ensure CSRF header injection for POST
                // Login ignores body and reads username from query
                body: mode === 'login' ? JSON.stringify({}) : JSON.stringify({ username, password }),
                auth: true, // Changed to true to ensure Origin header is sent
            });

            console.log('🔐 FRONTEND_LOGIN_STEP_5: API response received:', {
                status: response.status,
                statusText: response.statusText,
                ok: response.ok
            });

            console.info('LOGIN api.response', {
                status: response.status,
                statusText: response.statusText,
                ok: response.ok,
                headers: Object.fromEntries(response.headers.entries()),
                timestamp: new Date().toISOString(),
            });

            if (response.ok) {
                const data = await response.json().catch(() => null);
                console.info('LOGIN api.success', {
                    dataType: typeof data,
                    dataIsNull: data === null,
                    dataIsUndefined: data === undefined,
                    dataKeys: data ? Object.keys(data) : [],
                    hasAccessToken: data && !!data.access_token,
                    hasRefreshToken: data && !!data.refresh_token,
                    accessTokenLength: data && data.access_token?.length || 0,
                    refreshTokenLength: data && data.refresh_token?.length || 0,
                    timestamp: new Date().toISOString(),
                });

                console.log('🔐 FRONTEND_LOGIN_STEP_6: Processing successful response');
                console.log('🔐 FRONTEND_LOGIN_STEP_7: Response data:', data);

                if (isHeaderMode) {
                    console.log('🔐 FRONTEND_LOGIN_STEP_8: Header mode - checking for tokens in response body');
                    // In header mode, backend should return tokens in the body
                    if (!data || !data.access_token) {
                        console.error('🔐 FRONTEND_LOGIN_ERROR: Missing tokens in header mode', {
                            data,
                            dataType: typeof data,
                            timestamp: new Date().toISOString(),
                        });
                        setError('Login failed: Missing tokens (header mode)');
                        return;
                    }
                    console.log('🔐 FRONTEND_LOGIN_STEP_9: Setting tokens from response body');
                    setTokens(data.access_token, data.refresh_token);
                    console.log('🔐 FRONTEND_LOGIN_STEP_10: Bumping auth epoch');
                    bumpAuthEpoch();
                }

                console.info('LOGIN tokens.set', {
                    authEpochBumped: true,
                    timestamp: new Date().toISOString(),
                });

                console.log('🔐 LOGIN: Cookies after token setting:', document.cookie);

                // Debug: record login OK and echo cookies from server
                try {
                    logAuth('LOGIN_OK', { status: response.status });
                    const dbgRes = await apiFetch('/v1/debug/cookies', { method: 'GET', credentials: 'include' } as any);
                    const dbg = await dbgRes.json().catch(() => ({}));
                    logAuth('DEBUG_COOKIES', dbg);
                } catch { /* noop */ }

                // Trigger Auth Orchestrator refresh after successful login
                const authOrchestrator = getAuthOrchestrator();
                console.info('LOGIN orchestrator.refresh.start', {
                    timestamp: new Date().toISOString(),
                });

                // Get state before refresh
                const stateBefore = authOrchestrator.getState();
                console.log('LOGIN auth.state.before_refresh', {
                    isAuthenticated: stateBefore.is_authenticated,
                    sessionReady: stateBefore.session_ready,
                    userId: stateBefore.user_id,
                    timestamp: new Date().toISOString(),
                });

                await authOrchestrator.onLoginSuccess();

                // Get state after refresh
                const stateAfter = authOrchestrator.getState();
                console.log('LOGIN auth.state.after_refresh', {
                    isAuthenticated: stateAfter.is_authenticated,
                    sessionReady: stateAfter.session_ready,
                    userId: stateAfter.user_id,
                    timestamp: new Date().toISOString(),
                });

                console.info('LOGIN orchestrator.refresh.complete', {
                    timestamp: new Date().toISOString(),
                });

                console.info('LOGIN navigation.start', {
                    next,
                    timestamp: new Date().toISOString(),
                });

                // Use safeNext to prevent redirect loops
                const redirectTo = safeNext(params?.get('next')) || '/';
                console.log('🔐 LOGIN: Navigating to:', redirectTo);
                router.replace(redirectTo);

                console.info('LOGIN complete.success', {
                    timestamp: new Date().toISOString(),
                });

                console.log('🔐 LOGIN: Login process completed successfully');
            } else {
                const errorData = await response.json().catch(() => ({}));
                console.error('LOGIN api.error', {
                    status: response.status,
                    statusText: response.statusText,
                    errorDetail: errorData.detail,
                    errorData,
                    timestamp: new Date().toISOString(),
                });
                console.log('🔐 LOGIN: Login failed with status:', response.status);
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

    // Show loading spinner while checking authentication
    if (checkingAuth) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
                    <p className="mt-4 text-gray-600 dark:text-gray-400">Checking authentication...</p>
                </div>
            </div>
        );
    }

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

                        {/* Mock Login Button for E2E Testing */}
                        {process.env.NODE_ENV === 'development' && (
                            <div className="mt-4">
                                <Button
                                    type="button"
                                    onClick={async () => {
                                        setError('');
                                        setLoading(true);
                                        try {
                                            // Mock successful login for testing
                                            setTokens('mock_access_token_e2e', 'mock_refresh_token_e2e');
                                            bumpAuthEpoch();
                                            const authOrchestrator = getAuthOrchestrator();
                                            await authOrchestrator.refreshAuth({ force: true });
                                            router.replace(safeNext(params?.get('next')) || '/');
                                        } catch (err) {
                                            setError('Mock login failed');
                                        } finally {
                                            setLoading(false);
                                        }
                                    }}
                                    disabled={loading}
                                    className="w-full flex justify-center py-2 px-4 border border-dashed rounded-md shadow-sm text-sm font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 disabled:opacity-50"
                                    data-testid="mock-login-button"
                                >
                                    {loading ? 'Processing...' : 'Mock Login (E2E Test)'}
                                </Button>
                            </div>
                        )}

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
