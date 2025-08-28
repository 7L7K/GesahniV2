'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { updateProfile, UserProfile, useProfile, listSessions, revokeSession, listPATs, createPAT, apiFetch } from '@/lib/api';
import { getBudget } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { useAuthState } from '@/hooks/useAuth';
import { useDeterministicAuth, type DeterministicAuthStatus } from '@/hooks/useDeterministicAuth';
import { unstable_noStore as noStore } from 'next/cache';
import Link from 'next/link';
import { toast } from '@/lib/toast';
import { ToastManager } from '@/components/ui/ToastManager';
import AuthHUD from '@/components/AuthHUD';
import { disconnectSpotify, getIntegrationsStatus } from '@/lib/api/integrations';

// Force dynamic rendering to prevent SSR issues
noStore();

// Integration status types
type IntegrationStatus = 'connected' | 'disconnected' | 'error' | 'loading';

interface IntegrationInfo {
    name: string;
    description: string;
    status: IntegrationStatus;
    connected: boolean;
    lastChecked?: Date;
    error?: string;
    actionUrl?: string;
    actionLabel?: string;
}

function SettingsPageInner() {
    const [profile, setProfile] = useState<UserProfile | null>(null);
    const { data, isLoading, error } = useProfile();
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);
    const [saveSuccess, setSaveSuccess] = useState(false);
    const [activeTab, setActiveTab] = useState('profile');
    const [expandedCard, setExpandedCard] = useState<string | null>(null);
    const router = useRouter();
    const authState = useAuthState();
    const deterministicAuth = useDeterministicAuth();
    const [spotifyLogoutLoading, setSpotifyLogoutLoading] = useState(false);
    const [spotifyLogoutError, setSpotifyLogoutError] = useState<string | null>(null);

    // Handle URL hash and auto-expand cards + Spotify OAuth bootstrap
    useEffect(() => {
        if (typeof window !== 'undefined') {
            const hash = window.location.hash;
            const urlParams = new URLSearchParams(window.location.search);

            // Check for Spotify OAuth parameters
            const spotifyConnected = urlParams.get('spotify') === 'connected';
            const spotifyError = urlParams.get('spotify_error');
            const hasSpotifyParams = hash === '#spotify' || spotifyConnected || spotifyError;

            if (hasSpotifyParams) {
                setActiveTab('integrations');
                setExpandedCard('spotify');

                // If Spotify OAuth parameters are present, do deterministic auth bootstrap
                if (spotifyConnected || spotifyError) {
                    console.log('🎵 SETTINGS: Spotify OAuth parameters detected, starting deterministic auth bootstrap');
                    deterministicAuth.ensureAuth().then(() => {
                        // After auth bootstrap completes, clear URL parameters
                        if (spotifyConnected) {
                            toast.success("Successfully connected to Spotify!");
                            if (typeof window !== 'undefined') {
                                const url = new URL(window.location.href);
                                url.searchParams.delete('spotify');
                                url.hash = '#spotify';
                                window.history.replaceState({}, '', url.toString());
                            }
                        } else if (spotifyError) {
                            toast.warning(`Spotify connection failed: ${spotifyError}`);
                        }
                    });
                }
            }
        }
    }, [deterministicAuth]); // Include deterministicAuth to ensure the effect runs when it's available

    // Old spotify parameter handling has been replaced with deterministic auth bootstrap
    // The new logic is in the useEffect above that handles both hash and query params

    // Integration status state
    const [integrations, setIntegrations] = useState<Record<string, IntegrationInfo>>({
        spotify: {
            name: 'Spotify',
            description: 'Music playback and control',
            status: 'loading',
            connected: false,
        },
        google: {
            name: 'Google',
            description: 'Gmail and Calendar access',
            status: 'loading',
            connected: false,
        },
        home_assistant: {
            name: 'Home Assistant',
            description: 'Smart home automation',
            status: 'loading',
            connected: false,
        }
    });

    useEffect(() => {
        if (data) setProfile(prev => ({ ...prev, ...data }));
    }, [data]);

    useEffect(() => {
        if (error) {
            console.error('Failed to load profile:', error);
            // Only redirect if unauthorized; otherwise show error state
            const message = (error as Error).message || '';
            if (/401|403/.test(message)) {
                router.push('/login');
            }
        }
    }, [error, router]);

    const [budget, setBudget] = useState<{ tts?: { spent_usd: number; cap_usd: number; ratio: number } } | null>(null);

    useEffect(() => {
        const fetchBudget = async () => {
            if (!authState.is_authenticated) return;
            getBudget().then((b) => setBudget(b as any)).catch(() => setBudget(null));
        };

        fetchBudget();
    }, [authState.is_authenticated]);

    // Check integration status - always call this hook regardless of auth state
    useEffect(() => {
        const checkIntegrations = async () => {
            if (!authState.is_authenticated) return;

            try {
                const res = await apiFetch('/v1/integrations/status', { credentials: 'include', auth: false });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();

                const sp = data.spotify || {};
                const gg = data.google || {};
                const ha = data.home_assistant || {};

                const spotifyConnected = Boolean(sp.connected || sp.linked);
                const googleConnected = Boolean(gg.connected || gg.linked);
                const haConnected = Boolean(ha.connected || ha.healthy);

                setIntegrations(prev => ({
                    ...prev,
                    spotify: { ...prev.spotify, status: spotifyConnected ? 'connected' : (sp.reason ? 'error' : 'disconnected'), connected: spotifyConnected, lastChecked: new Date(), error: sp.reason || undefined },
                    google: { ...prev.google, status: googleConnected ? 'connected' : (gg.reason ? 'error' : 'disconnected'), connected: googleConnected, lastChecked: new Date(), error: gg.reason || undefined },
                    home_assistant: { ...prev.home_assistant, status: haConnected ? 'connected' : (ha.reason ? 'error' : 'disconnected'), connected: haConnected, lastChecked: new Date(), error: ha.reason || undefined },
                }));
            } catch (err) {
                setIntegrations(prev => ({
                    ...prev,
                    spotify: { ...prev.spotify, status: 'error', connected: false, error: (err as Error).message, lastChecked: new Date() },
                    google: { ...prev.google, status: 'error', connected: false, error: (err as Error).message, lastChecked: new Date() },
                    home_assistant: { ...prev.home_assistant, status: 'error', connected: false, error: (err as Error).message, lastChecked: new Date() },
                }));
            }
        };

        checkIntegrations();
    }, [authState.is_authenticated]);

    const refreshIntegrationsFromServer = async () => {
        const data = await getIntegrationsStatus();
        const sp = data.spotify || {};
        const gg = data.google || {};
        const ha = data.home_assistant || {};

        const spotifyConnected = Boolean(sp.connected || sp.linked);
        const googleConnected = Boolean(gg.connected || gg.linked);
        const haConnected = Boolean(ha.connected || ha.healthy);

        setIntegrations(prev => ({
            ...prev,
            spotify: { ...prev.spotify, status: spotifyConnected ? 'connected' : (sp.reason ? 'error' : 'disconnected'), connected: spotifyConnected, lastChecked: new Date(), error: sp.reason || undefined },
            google: { ...prev.google, status: googleConnected ? 'connected' : (gg.reason ? 'error' : 'disconnected'), connected: googleConnected, lastChecked: new Date(), error: gg.reason || undefined },
            home_assistant: { ...prev.home_assistant, status: haConnected ? 'connected' : (ha.reason ? 'error' : 'disconnected'), connected: haConnected, lastChecked: new Date(), error: ha.reason || undefined },
        }));
    };

    const handleLogoutSpotify = async (e?: React.MouseEvent) => {
        e?.stopPropagation();
        setSpotifyLogoutError(null);
        setSpotifyLogoutLoading(true);
        try {
            await disconnectSpotify();
            await refreshIntegrationsFromServer();
            toast.success('Spotify disconnected');
        } catch (err: any) {
            const msg = err?.message ?? 'Failed to disconnect Spotify';
            setSpotifyLogoutError(msg);
            toast.error(msg);
        } finally {
            setSpotifyLogoutLoading(false);
        }
    };

    const handleSave = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!profile) return;

        setSaving(true);
        setSaveSuccess(false);
        setSaveError(null);
        try {
            await updateProfile(profile);
            setSaveSuccess(true);
        } catch (error) {
            console.error('Failed to update profile:', error);
            const msg = error instanceof Error ? error.message : 'Failed to update profile. Please try again.';
            setSaveError(msg);
        } finally {
            setSaving(false);
        }
    };

    const handleChange = (field: keyof UserProfile, value: unknown) => {
        if (profile) {
            setProfile(prev => prev ? { ...prev, [field]: value } : null);
        }
    };

    // Show loading while checking auth
    if (authState.isLoading) {
        const isSpotifyOAuth = hasSpotifyParams;
        return (
            <main className="min-h-screen bg-gray-50 flex items-center justify-center">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
                    <p className="text-gray-600">
                        {isSpotifyOAuth ? 'Completing Spotify connection...' : 'Checking authentication...'}
                    </p>
                    {isSpotifyOAuth && (
                        <p className="text-sm text-gray-500 mt-2">Please wait while we finalize your Spotify integration.</p>
                    )}
                </div>
            </main>
        );
    }

    // TEMPORARILY DISABLED: Redirect if not authenticated (with Spotify OAuth handling)
    // This is commented out for 10 minutes to debug the redirect loop
    const [redirectsDisabled, setRedirectsDisabled] = useState(true);
    const [timeRemaining, setTimeRemaining] = useState(600); // 10 minutes in seconds

    // Auto-re-enable redirects after 10 minutes
    useEffect(() => {
        const timer = setInterval(() => {
            setTimeRemaining(prev => {
                if (prev <= 1) {
                    setRedirectsDisabled(false);
                    clearInterval(timer);
                    return 0;
                }
                return prev - 1;
            });
        }, 1000);

        return () => clearInterval(timer);
    }, []);

    // Format time remaining
    const formatTime = (seconds: number) => {
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
    };

    /*
    // ORIGINAL REDIRECT LOGIC - DISABLED FOR DEBUGGING
    useEffect(() => {
        if (typeof window !== 'undefined') {
            const urlParams = new URLSearchParams(window.location.search);
            const spotifyConnected = urlParams.get('spotify') === 'connected';
            const spotifyError = urlParams.get('spotify_error');

            // If we have Spotify OAuth parameters, wait longer before redirecting
            // to allow auth refresh to complete
            if (spotifyConnected || spotifyError) {
                console.log('🎵 SETTINGS: Spotify OAuth detected, delaying auth redirect check');

                // Delay the auth check to allow refresh to complete
                const timer = setTimeout(() => {
                    if (!authState.is_authenticated) {
                        console.log('🎵 SETTINGS: Auth still not ready after Spotify OAuth, redirecting to login');
                        router.replace('/login?next=%2Fsettings');
                    }
                }, 3000); // Wait 3 seconds for auth refresh

                return () => clearTimeout(timer);
            }
        }

        // Normal auth check for non-Spotify flows
        if (!authState.is_authenticated) {
            router.replace('/login?next=%2Fsettings');
        }
    }, [authState.is_authenticated, router]);
    */

    // Show authentication status instead of redirecting
    const urlParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
    const hasSpotifyParams = urlParams?.get('spotify') === 'connected' || urlParams?.get('spotify_error');

    // Show loading while checking auth (use deterministic auth for Spotify OAuth)
    if (authState.isLoading || (hasSpotifyParams && deterministicAuth.status === 'checking')) {
        const isSpotifyOAuth = hasSpotifyParams;
        return (
            <main className="min-h-screen bg-gray-50 flex items-center justify-center">
                <div className="text-center space-y-4">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
                    <div>
                        <p className="text-gray-600 font-medium">
                            {isSpotifyOAuth ? 'Completing Spotify connection...' : 'Checking authentication...'}
                        </p>
                        <p className="text-sm text-gray-500 mt-2">
                            {isSpotifyOAuth ? 'Please wait while we finalize your Spotify integration.' : 'Verifying your login status...'}
                        </p>
                    </div>
                    <div className="text-xs text-gray-400 space-y-1">
                        <p>Auth State: {authState.is_authenticated ? '✅ Authenticated' : '❌ Not Authenticated'}</p>
                        <p>Loading: {authState.isLoading ? '🔄' : '✅'}</p>
                        <p>User ID: {authState.user_id || 'none'}</p>
                        <p>Session Ready: {authState.session_ready ? '✅' : '❌'}</p>
                        <p>Source: {authState.source}</p>
                        {hasSpotifyParams && (
                            <>
                                <p className="text-blue-500">Spotify OAuth detected in URL</p>
                                <p>Deterministic Auth: {deterministicAuth.status === 'checking' ? '🔄 Checking' :
                                    deterministicAuth.status === 'authenticated' ? '✅ Authenticated' :
                                        '❌ Failed'}</p>
                            </>
                        )}
                        <p>Redirects: {redirectsDisabled ? `⏸️ Disabled (${formatTime(timeRemaining)})` : '▶️ Enabled'}</p>
                    </div>
                </div>
            </main>
        );
    }

    // Show authentication status screen instead of redirecting
    if (!authState.is_authenticated && !(hasSpotifyParams && deterministicAuth.status === 'authenticated')) {
        const isSpotifyOAuthFailure = hasSpotifyParams && deterministicAuth.status === 'unauthenticated';

        return (
            <main className="min-h-screen bg-gray-50 flex items-center justify-center">
                <div className="max-w-md mx-auto text-center space-y-6 p-8 bg-white rounded-lg shadow-lg">
                    <div className="text-6xl">{isSpotifyOAuthFailure ? '🎵' : '🔐'}</div>
                    <div>
                        <h1 className="text-2xl font-bold text-gray-900 mb-2">
                            {isSpotifyOAuthFailure ? 'Spotify Connection Issue' : 'Authentication Status'}
                        </h1>
                        <p className="text-gray-600">
                            {isSpotifyOAuthFailure
                                ? 'We couldn\'t complete your Spotify connection. You may need to log in again.'
                                : 'You are currently not authenticated'
                            }
                        </p>
                    </div>

                    <div className="space-y-3 text-left bg-gray-50 p-4 rounded">
                        <div className="text-sm">
                            <strong>Auth State:</strong> {authState.is_authenticated ? '✅ Authenticated' : '❌ Not Authenticated'}
                        </div>
                        <div className="text-sm">
                            <strong>User ID:</strong> {authState.user_id || 'none'}
                        </div>
                        <div className="text-sm">
                            <strong>Session Ready:</strong> {authState.session_ready ? '✅' : '❌'}
                        </div>
                        <div className="text-sm">
                            <strong>Source:</strong> {authState.source}
                        </div>
                        {hasSpotifyParams && (
                            <>
                                <div className="text-sm text-blue-500">
                                    <strong>Spotify OAuth:</strong> Detected in URL parameters
                                </div>
                                <div className="text-sm">
                                    <strong>Deterministic Auth:</strong> {
                                        deterministicAuth.status === 'checking' ? '🔄 Checking' :
                                            deterministicAuth.status === 'authenticated' ? '✅ Authenticated' :
                                                '❌ Failed'
                                    }
                                </div>
                            </>
                        )}
                        {authState.error && (
                            <div className="text-sm text-red-500">
                                <strong>Error:</strong> {authState.error}
                            </div>
                        )}
                    </div>

                    <div className="space-y-3">
                        <Button
                            onClick={() => window.location.href = '/login?next=%2Fsettings'}
                            className="w-full"
                        >
                            {isSpotifyOAuthFailure ? 'Login & Try Spotify Again' : 'Go to Login'}
                        </Button>
                        <Button
                            onClick={() => window.location.reload()}
                            variant="outline"
                            className="w-full"
                        >
                            Refresh Page
                        </Button>
                        {isSpotifyOAuthFailure && (
                            <Button
                                onClick={() => {
                                    // Clear Spotify params and go to integrations
                                    if (typeof window !== 'undefined') {
                                        const url = new URL(window.location.href);
                                        url.searchParams.delete('spotify');
                                        url.searchParams.delete('spotify_error');
                                        url.hash = '#spotify';
                                        window.history.replaceState({}, '', url.toString());
                                        window.location.reload();
                                    }
                                }}
                                variant="outline"
                                className="w-full"
                            >
                                Clear Spotify Params & Retry
                            </Button>
                        )}
                    </div>

                    <div className="text-xs text-gray-400 space-y-1">
                        <p>Redirects: {redirectsDisabled ? `⏸️ Disabled (${formatTime(timeRemaining)} remaining)` : '▶️ Enabled'}</p>
                        <p>Auto-re-enable: {redirectsDisabled ? 'Yes' : 'No'}</p>
                    </div>
                </div>
            </main>
        );
    }


    // Show loading if profile is still loading
    if (!profile) {
        return (
            <main className="min-h-screen bg-gray-50 flex items-center justify-center">
                <div className="text-center space-y-4">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto"></div>
                    <p className="text-gray-600">Loading your profile...</p>
                </div>
            </main>
        );
    }

    // Tab configuration
    const tabs = [
        { id: 'profile', name: 'Profile', icon: '👤' },
        { id: 'integrations', name: 'Integrations', icon: '🔗' },
        { id: 'security', name: 'Security', icon: '🔒' },
        { id: 'usage', name: 'Usage & Billing', icon: '📊' },
    ];

    const getStatusIcon = (status: IntegrationStatus) => {
        switch (status) {
            case 'connected': return '🟢';
            case 'disconnected': return '⚪';
            case 'error': return '🔴';
            case 'loading': return '🟡';
        }
    };

    const getStatusColor = (status: IntegrationStatus) => {
        switch (status) {
            case 'connected': return 'text-green-600 bg-green-50 border-green-200';
            case 'disconnected': return 'text-gray-600 bg-gray-50 border-gray-200';
            case 'error': return 'text-red-600 bg-red-50 border-red-200';
            case 'loading': return 'text-yellow-600 bg-yellow-50 border-yellow-200';
        }
    };

    return (
        <main className="min-h-screen bg-gray-50">
            {/* Debug HUD - only shows in development */}
            <AuthHUD />

            {/* Toast Manager */}
            <ToastManager />

            {/* Header */}
            <div className="bg-white border-b border-gray-200">
                <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex items-center justify-between h-16">
                        <div className="flex items-center space-x-4">
                            <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
                            <span className="text-sm text-gray-500">Manage your account and preferences</span>
                        </div>
                        <div className="flex items-center space-x-3">
                            <Link href="/admin">
                                <Button variant="outline" size="sm" className="hidden md:flex">
                                    🔧 Admin Panel
                                </Button>
                            </Link>
                            <Button onClick={() => router.push('/')} variant="outline" size="sm">
                                Back to Chat
                            </Button>
                        </div>
                    </div>
                </div>
            </div>

            <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                {/* Tab Navigation */}
                <div className="mb-8">
                    <nav className="flex space-x-1 bg-gray-100 p-1 rounded-lg">
                        {tabs.map((tab) => (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`flex items-center space-x-2 px-4 py-2 text-sm font-medium rounded-md transition-colors ${activeTab === tab.id
                                    ? 'bg-white text-gray-900 shadow-sm'
                                    : 'text-gray-600 hover:text-gray-900'
                                    }`}
                            >
                                <span>{tab.icon}</span>
                                <span>{tab.name}</span>
                                {tab.id === 'integrations' && (
                                    <span className="ml-2 flex space-x-1">
                                        {Object.values(integrations).map((integration, i) => (
                                            <span
                                                key={i}
                                                className="w-2 h-2 rounded-full"
                                                title={`${integration.name}: ${integration.status}`}
                                            >
                                                {integration.status === 'connected' && '🟢'}
                                                {integration.status === 'disconnected' && '⚪'}
                                                {integration.status === 'error' && '🔴'}
                                                {integration.status === 'loading' && '🟡'}
                                            </span>
                                        ))}
                                    </span>
                                )}
                            </button>
                        ))}
                    </nav>
                </div>

                {/* Tab Content */}
                <div className="bg-white rounded-lg shadow-sm border border-gray-200">
                    {activeTab === 'profile' && (
                        <form onSubmit={handleSave} className="p-6 space-y-8">
                            {/* Success/Error Messages */}
                            {saveSuccess && (
                                <div className="bg-green-50 border border-green-200 rounded-md p-4">
                                    <div className="flex items-center">
                                        <span className="text-green-800">✓ Profile updated successfully.</span>
                                    </div>
                                </div>
                            )}
                            {saveError && (
                                <div className="bg-red-50 border border-red-200 rounded-md p-4">
                                    <div className="flex items-center">
                                        <span className="text-red-800">✗ {saveError}</span>
                                    </div>
                                </div>
                            )}

                            {/* Basic Information */}
                            <div className="space-y-6">
                                <div className="flex items-center space-x-2">
                                    <h2 className="text-lg font-semibold text-gray-900">Basic Information</h2>
                                    <span className="text-sm text-gray-500">Personal details and preferences</span>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    <div>
                                        <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2">
                                            Full Name
                                        </label>
                                        <input
                                            type="text"
                                            id="name"
                                            value={profile.name || ''}
                                            onChange={(e) => handleChange('name', e.target.value)}
                                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                                            placeholder="Enter your full name"
                                        />
                                    </div>

                                    <div>
                                        <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
                                            Email Address
                                        </label>
                                        <input
                                            type="email"
                                            id="email"
                                            value={profile.email || ''}
                                            onChange={(e) => handleChange('email', e.target.value)}
                                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                                        />
                                    </div>

                                    <div>
                                        <label htmlFor="timezone" className="block text-sm font-medium text-gray-700 mb-2">
                                            Timezone
                                        </label>
                                        <select
                                            id="timezone"
                                            value={profile.timezone || 'America/New_York'}
                                            onChange={(e) => handleChange('timezone', e.target.value)}
                                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                                        >
                                            <option value="America/New_York">Eastern Time (ET)</option>
                                            <option value="America/Chicago">Central Time (CT)</option>
                                            <option value="America/Denver">Mountain Time (MT)</option>
                                            <option value="America/Los_Angeles">Pacific Time (PT)</option>
                                            <option value="Europe/London">London (GMT)</option>
                                            <option value="Europe/Paris">Paris (CET)</option>
                                            <option value="Asia/Tokyo">Tokyo (JST)</option>
                                            <option value="Australia/Sydney">Sydney (AEDT)</option>
                                        </select>
                                    </div>

                                    <div>
                                        <label htmlFor="language" className="block text-sm font-medium text-gray-700 mb-2">
                                            Preferred Language
                                        </label>
                                        <select
                                            id="language"
                                            value={profile.language || 'en'}
                                            onChange={(e) => handleChange('language', e.target.value)}
                                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                                        >
                                            <option value="en">🇺🇸 English</option>
                                            <option value="es">🇪🇸 Spanish</option>
                                            <option value="fr">🇫🇷 French</option>
                                            <option value="de">🇩🇪 German</option>
                                            <option value="it">🇮🇹 Italian</option>
                                            <option value="pt">🇵🇹 Portuguese</option>
                                            <option value="ja">🇯🇵 Japanese</option>
                                            <option value="ko">🇰🇷 Korean</option>
                                            <option value="zh">🇨🇳 Chinese</option>
                                        </select>
                                    </div>
                                </div>
                            </div>

                            {/* AI Preferences */}
                            <div>
                                <h2 className="text-xl font-semibold text-gray-900 mb-6">AI Preferences</h2>
                                <div className="space-y-4">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-2">
                                            Communication Style
                                        </label>
                                        <div className="space-y-2">
                                            {[
                                                { id: 'casual', label: 'Casual & Friendly' },
                                                { id: 'formal', label: 'Professional & Formal' },
                                                { id: 'technical', label: 'Technical & Detailed' }
                                            ].map((style) => (
                                                <label key={style.id} className="flex items-center space-x-3">
                                                    <input
                                                        type="radio"
                                                        name="communication_style"
                                                        value={style.id}
                                                        checked={profile.communication_style === style.id}
                                                        onChange={(e) => handleChange('communication_style', e.target.value)}
                                                        className="text-indigo-600 focus:ring-indigo-500"
                                                    />
                                                    <span className="text-gray-700">{style.label}</span>
                                                </label>
                                            ))}
                                        </div>
                                    </div>

                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-2">
                                            Preferred AI Model
                                        </label>
                                        <div className="space-y-2">
                                            {[
                                                { id: 'auto', label: '🤖 Auto (Recommended)', desc: 'Let AI choose the best model' },
                                                { id: 'gpt-4o', label: '🚀 GPT-4o', desc: 'Latest GPT model, best quality' },
                                                { id: 'llama3', label: '🏠 LLaMA 3 (Local)', desc: 'Run locally, privacy focused' }
                                            ].map((model) => (
                                                <label key={model.id} className="flex items-start space-x-3 p-3 border rounded-lg hover:bg-gray-50 cursor-pointer">
                                                    <input
                                                        type="radio"
                                                        name="preferred_model"
                                                        value={model.id}
                                                        checked={(profile.preferred_model || 'auto') === model.id}
                                                        onChange={(e) => handleChange('preferred_model', e.target.value)}
                                                        className="mt-1 text-indigo-600 focus:ring-indigo-500"
                                                    />
                                                    <div className="flex-1">
                                                        <span className="text-gray-900 font-medium">{model.label}</span>
                                                        <p className="text-sm text-gray-500">{model.desc}</p>
                                                    </div>
                                                </label>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Voice & Budget */}
                            <div>
                                <h2 className="text-xl font-semibold text-gray-900 mb-6">Voice & Budget</h2>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    <div className="p-4 border rounded-lg">
                                        <div className="text-sm text-gray-600 mb-2">Monthly TTS Spend</div>
                                        <div className="h-2 bg-gray-200 rounded">
                                            {budget?.tts && (
                                                <div className={`h-2 rounded ${budget.tts.ratio >= 0.8 ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${Math.min(100, Math.round((budget.tts.ratio || 0) * 100))}%` }} />
                                            )}
                                        </div>
                                        <div className="mt-2 text-xs text-gray-600">
                                            {budget?.tts ? `~$${budget.tts.spent_usd.toFixed(2)} of $${budget.tts.cap_usd.toFixed(2)}` : '—'}
                                        </div>
                                    </div>
                                    <div className="p-4 border rounded-lg">
                                        <div className="text-sm text-gray-600 mb-2">Story Voice</div>
                                        <div className="text-xs text-gray-500">Switches to OpenAI TTS for expressive narration in Capture mode.</div>
                                    </div>
                                </div>
                            </div>

                            {/* Sessions */}
                            <div>
                                <h2 className="text-xl font-semibold text-gray-900 mb-6">Sessions</h2>
                                <SessionsPanel />
                            </div>

                            {/* Security */}
                            <div>
                                <h2 className="text-xl font-semibold text-gray-900 mb-6">Security</h2>
                                <PatPanel />
                            </div>

                            {/* Integrations */}
                            <div>
                                <h2 className="text-xl font-semibold text-gray-900 mb-6">Integrations</h2>
                                <div className="space-y-4">
                                    <div className="flex items-center justify-between p-4 border border-gray-200 rounded-lg">
                                        <div>
                                            <h3 className="font-medium text-gray-900">Gmail</h3>
                                            <p className="text-sm text-gray-600">Read and compose emails</p>
                                        </div>
                                        <label className="relative inline-flex items-center cursor-pointer">
                                            <input
                                                type="checkbox"
                                                checked={profile.gmail_integration || false}
                                                onChange={(e) => handleChange('gmail_integration', e.target.checked)}
                                                className="sr-only peer"
                                            />
                                            <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-indigo-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600"></div>
                                        </label>
                                    </div>

                                    <div className="flex items-center justify-between p-4 border border-gray-200 rounded-lg">
                                        <div>
                                            <h3 className="font-medium text-gray-900">Google Calendar</h3>
                                            <p className="text-sm text-gray-600">Schedule meetings and manage events</p>
                                        </div>
                                        <label className="relative inline-flex items-center cursor-pointer">
                                            <input
                                                type="checkbox"
                                                checked={profile.calendar_integration || false}
                                                onChange={(e) => handleChange('calendar_integration', e.target.checked)}
                                                className="sr-only peer"
                                            />
                                            <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-indigo-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600"></div>
                                        </label>
                                    </div>
                                </div>
                            </div>

                            {/* Voice & Audio Settings */}
                            <div className="space-y-6">
                                <div className="flex items-center space-x-2">
                                    <h2 className="text-lg font-semibold text-gray-900">Voice & Audio</h2>
                                    <span className="text-sm text-gray-500">TTS and audio preferences</span>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    <div className="p-4 border rounded-lg">
                                        <div className="text-sm text-gray-600 mb-2">🎵 Monthly TTS Budget</div>
                                        <div className="h-2 bg-gray-200 rounded">
                                            {budget?.tts && (
                                                <div className={`h-2 rounded ${budget.tts.ratio >= 0.8 ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${Math.min(100, Math.round((budget.tts.ratio || 0) * 100))}%` }} />
                                            )}
                                        </div>
                                        <div className="mt-2 text-xs text-gray-600">
                                            {budget?.tts ? `$${budget.tts.spent_usd.toFixed(2)} of $${budget.tts.cap_usd.toFixed(2)}` : 'No data available'}
                                        </div>
                                    </div>
                                    <div className="p-4 border rounded-lg">
                                        <div className="text-sm text-gray-600 mb-2">🔊 Voice Settings</div>
                                        <div className="text-xs text-gray-500">Switches to OpenAI TTS for expressive narration in Capture mode.</div>
                                    </div>
                                </div>
                            </div>

                            <div className="flex justify-end pt-6 border-t border-gray-200">
                                <Button
                                    type="submit"
                                    disabled={saving}
                                    className="bg-indigo-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-indigo-700 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50"
                                >
                                    {saving ? '💾 Saving...' : '💾 Save Changes'}
                                </Button>
                            </div>
                        </form>
                    )}

                    {/* Integrations Tab */}
                    {activeTab === 'integrations' && (
                        <div className="p-6 space-y-6">
                            <div className="flex items-center space-x-2 mb-6">
                                <h2 className="text-lg font-semibold text-gray-900">Connected Services</h2>
                                <span className="text-sm text-gray-500">Manage your connected apps and services</span>
                            </div>

                            <div className="grid gap-4">
                                {/* Spotify Integration */}
                                <div
                                    className={`border rounded-lg transition-all duration-300 cursor-pointer ${expandedCard === 'spotify' ? 'ring-2 ring-green-500 bg-green-50' : 'hover:bg-gray-50'}`}
                                    onClick={() => {
                                        const newExpanded = expandedCard === 'spotify' ? null : 'spotify';
                                        setExpandedCard(newExpanded);
                                        // Update URL hash for bookmarking
                                        if (typeof window !== 'undefined') {
                                            if (newExpanded === 'spotify') {
                                                window.history.replaceState(null, '', '#spotify');
                                            } else {
                                                // Remove hash if collapsing
                                                const url = new URL(window.location.href);
                                                url.hash = '';
                                                window.history.replaceState(null, '', url.toString());
                                            }
                                        }
                                    }}
                                >
                                    <div className="flex items-start justify-between">
                                        <div className="flex items-start space-x-4">
                                            <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center">
                                                <span className="text-2xl">🎵</span>
                                            </div>
                                            <div className="flex-1">
                                                <div className="flex items-center space-x-2">
                                                    <h3 className="text-lg font-medium text-gray-900">Spotify</h3>
                                                    <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium ${integrations.spotify.connected
                                                        ? 'bg-green-100 text-green-800 border border-green-200'
                                                        : 'bg-gray-100 text-gray-800 border border-gray-200'
                                                        }`}>
                                                        {integrations.spotify.connected ? '🟢 Connected' : '⚪ Not Connected'}
                                                    </span>
                                                </div>
                                                <p className="text-sm text-gray-600 mt-1">
                                                    {integrations.spotify.connected
                                                        ? 'Control your music playback, manage playlists, and access your Spotify library'
                                                        : 'Connect your Spotify account to control music playback and access your library'
                                                    }
                                                </p>
                                                {integrations.spotify.error && (
                                                    <p className="text-sm text-red-600 mt-2">⚠️ {integrations.spotify.error}</p>
                                                )}
                                                {integrations.spotify.lastChecked && (
                                                    <p className="text-xs text-gray-500 mt-1">
                                                        Last checked: {integrations.spotify.lastChecked.toLocaleTimeString()}
                                                    </p>
                                                )}
                                            </div>
                                        </div>
                                        <div className="flex items-center space-x-3">
                                            <span className={`text-gray-400 transition-transform duration-200 ${expandedCard === 'spotify' ? 'rotate-90' : ''}`}>
                                                ▶
                                            </span>
                                            {integrations.spotify.status === 'connected' ? (
                                                <div className="flex items-center space-x-2">
                                                    <Button variant="outline" size="sm" disabled={spotifyLogoutLoading} onClick={(e) => { e.stopPropagation(); window.open('/v1/spotify/status', '_blank'); }}>
                                                        🔗 Manage
                                                    </Button>
                                                    <Button
                                                        variant="outline"
                                                        className="px-3 py-2 text-red-600 hover:bg-red-50 rounded-md disabled:opacity-50"
                                                        size="sm"
                                                        disabled={spotifyLogoutLoading}
                                                        onClick={handleLogoutSpotify}
                                                    >
                                                        {spotifyLogoutLoading ? 'Logging out…' : 'Log out'}
                                                    </Button>
                                                </div>
                                            ) : !authState.is_authenticated ? (
                                                <Button
                                                    size="sm"
                                                    variant="outline"
                                                    disabled
                                                    onClick={(e) => { e.stopPropagation(); }}
                                                    title="Please log in first"
                                                >
                                                    🔒 Login Required
                                                </Button>
                                            ) : (
                                                <Button
                                                    size="sm"
                                                    onClick={async (e) => {
                                                        e.stopPropagation();

                                                        // Check if user is authenticated before attempting OAuth
                                                        if (!authState.is_authenticated) {
                                                            toast.error('Please log in first before connecting Spotify.');
                                                            return;
                                                        }

                                                        try {
                                                            // First make an authenticated request to get the authorization URL
                                                            const response = await apiFetch('/v1/spotify/connect', {
                                                                method: 'GET',
                                                                auth: true,
                                                                credentials: 'include',
                                                            });

                                                            if (response.ok) {
                                                                // If the response is successful, it should contain the auth URL
                                                                const data = await response.json().catch(() => null);
                                                                if (data && (data.auth_url || data.authorize_url)) {
                                                                    // Redirect to Spotify authorization (preserves session)
                                                                    window.location.href = data.auth_url || data.authorize_url;
                                                                } else {
                                                                    // Fallback: try to get location header
                                                                    const location = response.headers.get('Location');
                                                                    if (location) {
                                                                        window.location.href = location;
                                                                    }
                                                                }
                                                            } else if (response.status === 302) {
                                                                // Handle redirect response
                                                                const location = response.headers.get('Location');
                                                                if (location) {
                                                                    window.location.href = location;
                                                                }
                                                            }

                                                            // Refresh status after a delay
                                                            setTimeout(() => {
                                                                window.location.reload();
                                                            }, 3000);
                                                        } catch (error) {
                                                            console.error('Spotify connect error:', error);
                                                            toast.error('Failed to connect to Spotify. Please try again.');
                                                        }
                                                    }}
                                                >
                                                    🔗 {integrations.spotify.status === 'error' ? 'Try Again' : 'Connect'}
                                                </Button>
                                            )}
                                        </div>
                                    </div>

                                    {/* Expanded content */}
                                    {expandedCard === 'spotify' && (
                                        <div className="mt-4 p-4 bg-gray-50 rounded-lg border-t">
                                            {!authState.is_authenticated ? (
                                                <div>
                                                    <h4 className="text-sm font-medium text-amber-800 mb-3">🔐 Authentication Required</h4>
                                                    <p className="text-sm text-gray-600 mb-4">
                                                        You must be logged into Gesahni before connecting Spotify. Please sign in first to enable music integration features.
                                                    </p>
                                                    <div className="bg-amber-50 border border-amber-200 rounded p-3">
                                                        <div className="text-xs text-amber-700">
                                                            <strong>Note:</strong> Spotify OAuth requires an active Gesahni session to securely associate your Spotify account with your profile.
                                                        </div>
                                                    </div>
                                                </div>
                                            ) : integrations.spotify.connected ? (
                                                <div>
                                                    <h4 className="text-sm font-medium text-green-800 mb-3">🎵 Available Features:</h4>
                                                    <div className="grid grid-cols-2 gap-2 text-sm text-green-700 mb-4">
                                                        <span>✓ Play/Pause Music</span>
                                                        <span>✓ Skip Tracks</span>
                                                        <span>✓ Control Volume</span>
                                                        <span>✓ Device Selection</span>
                                                        <span>✓ Queue Management</span>
                                                        <span>✓ Current Track Info</span>
                                                    </div>
                                                    <div className="flex items-center space-x-2">
                                                        <Button variant="outline" size="sm" disabled={spotifyLogoutLoading} onClick={(e) => { e.stopPropagation(); window.open('/v1/spotify/status', '_blank'); }}>
                                                            🔗 Manage Connection
                                                        </Button>
                                                        <Button
                                                            className="px-3 py-2 text-red-600 hover:bg-red-50 rounded-md disabled:opacity-50"
                                                            variant="outline"
                                                            size="sm"
                                                            disabled={spotifyLogoutLoading}
                                                            onClick={handleLogoutSpotify}
                                                        >
                                                            {spotifyLogoutLoading ? 'Logging out…' : 'Log out'}
                                                        </Button>
                                                    </div>
                                                    {spotifyLogoutError && (
                                                        <p className="mt-2 text-sm text-red-600">{spotifyLogoutError}</p>
                                                    )}
                                                </div>
                                            ) : (
                                                <div>
                                                    <h4 className="text-sm font-medium text-gray-800 mb-3">🔗 Connect Spotify</h4>
                                                    <p className="text-sm text-gray-600 mb-4">
                                                        Connect your Spotify account to control music playback, manage playlists, and access your music library directly from this app.
                                                    </p>
                                                    <div className="text-xs text-gray-500 mb-4">
                                                        <strong>What you'll get:</strong>
                                                        <ul className="mt-1 space-y-1">
                                                            <li>• Control playback (play, pause, skip, volume)</li>
                                                            <li>• View current track and queue information</li>
                                                            <li>• Transfer playback between devices</li>
                                                            <li>• Access your playlists and saved tracks</li>
                                                        </ul>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>

                                {/* Google Integration */}
                                <div className="border rounded-lg p-6">
                                    <div className="flex items-start justify-between">
                                        <div className="flex items-start space-x-4">
                                            <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center">
                                                <span className="text-2xl">📧</span>
                                            </div>
                                            <div className="flex-1">
                                                <div className="flex items-center space-x-2">
                                                    <h3 className="text-lg font-medium text-gray-900">Google</h3>
                                                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(integrations.google.status)}`}>
                                                        {getStatusIcon(integrations.google.status)} {integrations.google.status}
                                                    </span>
                                                </div>
                                                <p className="text-sm text-gray-600 mt-1">{integrations.google.description}</p>
                                                {integrations.google.error && (
                                                    <p className="text-sm text-red-600 mt-2">⚠️ {integrations.google.error}</p>
                                                )}
                                            </div>
                                        </div>
                                        <div className="flex items-center space-x-3">
                                            <Button variant="outline" size="sm" disabled>
                                                🔗 Auto-connected
                                            </Button>
                                        </div>
                                    </div>

                                    {/* Features when connected */}
                                    {integrations.google.status === 'connected' && (
                                        <div className="mt-4 p-4 bg-blue-50 rounded-lg">
                                            <h4 className="text-sm font-medium text-blue-800 mb-2">📧 Available Features:</h4>
                                            <div className="grid grid-cols-2 gap-2 text-sm text-blue-700">
                                                <span>✓ Gmail Access</span>
                                                <span>✓ Calendar Events</span>
                                                <span>✓ Email Composition</span>
                                                <span>✓ Meeting Scheduling</span>
                                            </div>
                                        </div>
                                    )}
                                </div>

                                {/* Home Assistant Integration */}
                                <div className="border rounded-lg p-6">
                                    <div className="flex items-start justify-between">
                                        <div className="flex items-start space-x-4">
                                            <div className="w-12 h-12 bg-orange-100 rounded-lg flex items-center justify-center">
                                                <span className="text-2xl">🏠</span>
                                            </div>
                                            <div className="flex-1">
                                                <div className="flex items-center space-x-2">
                                                    <h3 className="text-lg font-medium text-gray-900">Home Assistant</h3>
                                                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(integrations.home_assistant.status)}`}>
                                                        {getStatusIcon(integrations.home_assistant.status)} {integrations.home_assistant.status}
                                                    </span>
                                                </div>
                                                <p className="text-sm text-gray-600 mt-1">{integrations.home_assistant.description}</p>
                                                {integrations.home_assistant.error && (
                                                    <p className="text-sm text-red-600 mt-2">⚠️ {integrations.home_assistant.error}</p>
                                                )}
                                            </div>
                                        </div>
                                        <div className="flex items-center space-x-3">
                                            <Button variant="outline" size="sm" disabled>
                                                ⚙️ Configure
                                            </Button>
                                        </div>
                                    </div>

                                    {/* Features when connected */}
                                    {integrations.home_assistant.status === 'connected' && (
                                        <div className="mt-4 p-4 bg-orange-50 rounded-lg">
                                            <h4 className="text-sm font-medium text-orange-800 mb-2">🏠 Available Features:</h4>
                                            <div className="grid grid-cols-2 gap-2 text-sm text-orange-700">
                                                <span>✓ Control Lights</span>
                                                <span>✓ Smart Home Devices</span>
                                                <span>✓ Climate Control</span>
                                                <span>✓ Security Systems</span>
                                                <span>✓ Media Players</span>
                                                <span>✓ Energy Monitoring</span>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Connection Help */}
                            <div className="mt-8 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                                <h3 className="text-sm font-medium text-blue-800 mb-2">🔗 Need Help Connecting?</h3>
                                <div className="text-sm text-blue-700 space-y-1">
                                    <p><strong>Spotify:</strong> Visit the Spotify Developer Console to create an app and get credentials</p>
                                    <p><strong>Google:</strong> Automatically connected when you sign in with Google</p>
                                    <p><strong>Home Assistant:</strong> Start your HA instance and configure the API token</p>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Security Tab */}
                    {activeTab === 'security' && (
                        <div className="p-6 space-y-6">
                            <div className="flex items-center space-x-2 mb-6">
                                <h2 className="text-lg font-semibold text-gray-900">Security & Access</h2>
                                <span className="text-sm text-gray-500">Manage your sessions and API access</span>
                            </div>

                            {/* Sessions Management */}
                            <div className="space-y-4">
                                <div className="flex items-center space-x-2">
                                    <h3 className="text-md font-medium text-gray-900">Active Sessions</h3>
                                    <span className="text-sm text-gray-500">Devices logged into your account</span>
                                </div>
                                <SessionsPanel />
                            </div>

                            {/* Personal Access Tokens */}
                            <div className="space-y-4">
                                <div className="flex items-center space-x-2">
                                    <h3 className="text-md font-medium text-gray-900">API Access Tokens</h3>
                                    <span className="text-sm text-gray-500">Generate tokens for API access</span>
                                </div>
                                <PatPanel />
                            </div>

                            {/* Security Tips */}
                            <div className="mt-8 p-4 bg-amber-50 border border-amber-200 rounded-lg">
                                <h3 className="text-sm font-medium text-amber-800 mb-2">🛡️ Security Tips</h3>
                                <div className="text-sm text-amber-700 space-y-1">
                                    <p>• Regularly revoke unused sessions from unfamiliar devices</p>
                                    <p>• Use Personal Access Tokens with limited scopes for API access</p>
                                    <p>• Monitor your account activity through the sessions list</p>
                                    <p>• Enable two-factor authentication when available</p>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Usage & Billing Tab */}
                    {activeTab === 'usage' && (
                        <div className="p-6 space-y-6">
                            <div className="flex items-center space-x-2 mb-6">
                                <h2 className="text-lg font-semibold text-gray-900">Usage & Billing</h2>
                                <span className="text-sm text-gray-500">Monitor your AI usage and costs</span>
                            </div>

                            {/* Budget Overview */}
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                <div className="bg-gradient-to-br from-blue-50 to-blue-100 p-6 rounded-lg border border-blue-200">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <p className="text-sm font-medium text-blue-900">Monthly Budget</p>
                                            <p className="text-2xl font-bold text-blue-900">${budget?.tts?.cap_usd.toFixed(2) || '15.00'}</p>
                                        </div>
                                        <span className="text-2xl">💰</span>
                                    </div>
                                </div>

                                <div className="bg-gradient-to-br from-green-50 to-green-100 p-6 rounded-lg border border-green-200">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <p className="text-sm font-medium text-green-900">Used This Month</p>
                                            <p className="text-2xl font-bold text-green-900">${budget?.tts?.spent_usd.toFixed(2) || '0.00'}</p>
                                        </div>
                                        <span className="text-2xl">📊</span>
                                    </div>
                                </div>

                                <div className="bg-gradient-to-br from-purple-50 to-purple-100 p-6 rounded-lg border border-purple-200">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <p className="text-sm font-medium text-purple-900">Remaining</p>
                                            <p className="text-2xl font-bold text-purple-900">
                                                ${budget?.tts ? (budget.tts.cap_usd - budget.tts.spent_usd).toFixed(2) : '15.00'}
                                            </p>
                                        </div>
                                        <span className="text-2xl">🎯</span>
                                    </div>
                                </div>
                            </div>

                            {/* Detailed Usage */}
                            <div className="space-y-4">
                                <h3 className="text-md font-medium text-gray-900">Usage Breakdown</h3>
                                <div className="border rounded-lg overflow-hidden">
                                    <div className="p-4 border-b border-gray-200">
                                        <div className="text-sm text-gray-600 mb-2">🎵 Text-to-Speech Usage</div>
                                        <div className="h-3 bg-gray-200 rounded">
                                            {budget?.tts && (
                                                <div className={`h-3 rounded transition-all duration-300 ${budget.tts.ratio >= 0.8 ? 'bg-red-500' : budget.tts.ratio >= 0.6 ? 'bg-yellow-500' : 'bg-green-500'}`} style={{ width: `${Math.min(100, Math.round((budget.tts.ratio || 0) * 100))}%` }} />
                                            )}
                                        </div>
                                        <div className="mt-2 flex justify-between text-xs text-gray-600">
                                            <span>Used: ${budget?.tts?.spent_usd.toFixed(2) || '0.00'}</span>
                                            <span>Limit: ${budget?.tts?.cap_usd.toFixed(2) || '15.00'}</span>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Billing Information */}
                            <div className="mt-8 p-4 bg-gray-50 border border-gray-200 rounded-lg">
                                <h3 className="text-sm font-medium text-gray-900 mb-2">💳 Billing Information</h3>
                                <div className="text-sm text-gray-600 space-y-1">
                                    <p>• Monthly billing cycle resets on the 1st</p>
                                    <p>• Usage is tracked in real-time</p>
                                    <p>• Get notified at 80% and 100% of budget</p>
                                    <p>• Upgrade anytime for higher limits</p>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </main>
    );
}

function SessionsPanel() {
    const [items, setItems] = useState<{ session_id: string; device_id: string; device_name?: string; created_at?: number; last_seen_at?: number; current?: boolean }[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    useEffect(() => {
        listSessions()
            .then((res) => { setItems(Array.isArray(res) ? res : []); console.log('items raw:', res); })
            .catch((e) => setError(e?.message || 'failed'))
            .finally(() => setLoading(false));
    }, []);
    useEffect(() => { console.log('items state (sessions):', items); }, [items]);
    const onRevoke = async (sid: string) => {
        try { await revokeSession(sid); setItems((prev) => prev.filter((s) => s.session_id !== sid)); } catch { /* ignore */ }
    };
    if (loading) return <div className="text-sm text-gray-500">Loading sessions…</div>;
    if (error) return <div className="text-sm text-red-600">{error}</div>;
    if (!Array.isArray(items) || items.length === 0) return <div className="text-sm text-gray-500">No active sessions</div>;
    return (
        <div className="space-y-3">
            {Array.isArray(items) ? items.map((s, i) => (
                <div key={s.session_id || `${s.device_id}:${s.created_at || s.last_seen_at || i}`}
                    className="flex items-center justify-between p-3 border rounded">
                    <div className="text-sm">
                        <div className="font-medium">{s.device_name || s.device_id}</div>
                        <div className="text-gray-500">Created: {s.created_at ? new Date(s.created_at * 1000).toLocaleString() : '—'} · Last seen: {s.last_seen_at ? new Date(s.last_seen_at * 1000).toLocaleString() : '—'}</div>
                        {s.current ? <div className="text-xs text-emerald-600">This device</div> : null}
                    </div>
                    {!s.current && (
                        <button onClick={() => onRevoke(s.session_id)} className="text-sm text-red-600 hover:underline">Revoke</button>
                    )}
                </div>
            )) : null}
        </div>
    );
}

function PatPanel() {
    const [items, setItems] = useState<{ id: string; name: string; scopes: string[]; exp_at?: number | null; last_used_at?: number | null }[]>([]);
    const [name, setName] = useState('');
    const [scopes, setScopes] = useState('');
    const [creating, setCreating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    useEffect(() => { listPATs().then((res) => { setItems(Array.isArray(res) ? res : []); console.log('items raw:', res); }).catch((e) => setError(e?.message || 'failed')); }, []);
    useEffect(() => { console.log('items state (pats):', items); }, [items]);
    const onCreate = async () => {
        setCreating(true); setError(null);
        try {
            const s = scopes.split(',').map(s => s.trim()).filter(Boolean);
            const res = await createPAT(name || 'New PAT', s);
            setItems((prev) => [{ id: res.id, name: name || 'New PAT', scopes: s }, ...prev]);
            setName(''); setScopes('');
        } catch (e: any) {
            setError(e?.message || 'failed');
        } finally { setCreating(false); }
    };
    return (
        <div className="space-y-4">
            <div className="flex items-end gap-3">
                <div className="flex-1">
                    <label className="block text-sm text-gray-700 mb-1">Name</label>
                    <input value={name} onChange={(e) => setName(e.target.value)} className="w-full px-3 py-2 border rounded" />
                </div>
                <div className="flex-1">
                    <label className="block text-sm text-gray-700 mb-1">Scopes (comma-separated)</label>
                    <input value={scopes} onChange={(e) => setScopes(e.target.value)} className="w-full px-3 py-2 border rounded" />
                </div>
                <Button onClick={onCreate} disabled={creating || !name} className="min-w-[120px]">{creating ? 'Creating…' : 'Create PAT'}</Button>
            </div>
            {error && <div className="text-sm text-red-600">{error}</div>}
            <div className="space-y-2">
                {Array.isArray(items) && items.length > 0 ? (
                    items.map((p) => (
                        <div key={p.id} className="p-3 border rounded text-sm">
                            <div className="font-medium">{p.name}</div>
                            <div className="text-gray-600">Scopes: {p.scopes.join(', ') || '—'}</div>
                            {typeof p.last_used_at === 'number' && <div className="text-gray-500">Last used: {new Date((p.last_used_at as number) * 1000).toLocaleString()}</div>}
                        </div>
                    ))
                ) : (
                    <div className="text-sm text-gray-500">No personal tokens yet</div>
                )}
            </div>
        </div>
    );
}

export default function SettingsPage() {
    const [mounted, setMounted] = useState(false);
    useEffect(() => { setMounted(true); }, []);
    if (!mounted) {
        return (
            <main className="min-h-screen bg-gray-50 flex items-center justify-center">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
                    <p className="text-gray-600">Loading…</p>
                </div>
            </main>
        );
    }
    return (
        <Suspense fallback={
            <main className="min-h-screen bg-gray-50 flex items-center justify-center">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
                    <p className="text-gray-600">Loading...</p>
                </div>
            </main>
        }>
            <SettingsPageInner />
        </Suspense>
    );
}
