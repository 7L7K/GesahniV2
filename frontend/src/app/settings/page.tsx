'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { updateProfile, UserProfile, useProfile } from '@/lib/api';
import { getBudget } from '@/lib/api';
import { Button } from '@/components/ui/button';

function SettingsPageInner() {
    const [profile, setProfile] = useState<UserProfile | null>(null);
    const { data, isLoading, error } = useProfile();
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);
    const [saveSuccess, setSaveSuccess] = useState(false);
    const router = useRouter();

    useEffect(() => {
        if (error) {
            console.error('Failed to load profile:', error);
            // Only redirect if unauthorized; otherwise show error state
            const message = (error as Error).message || '';
            if (/401|403/.test(message)) {
                router.push('/login');
            }
        }
        if (data) setProfile(prev => ({ ...prev, ...data }));
    }, [router, data, error]);

    const [budget, setBudget] = useState<{ tts?: { spent_usd: number; cap_usd: number; ratio: number } } | null>(null);

    useEffect(() => {
        getBudget().then((b) => setBudget(b as any)).catch(() => setBudget(null));
    }, []);

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

    if (isLoading) {
        return (
            <main className="min-h-screen bg-gray-50 flex items-center justify-center">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
                    <p className="text-gray-600">Loading settings...</p>
                </div>
            </main>
        );
    }

    if (!profile) {
        return (
            <main className="min-h-screen bg-gray-50 flex items-center justify-center">
                <div className="text-center">
                    <p className="text-gray-600">Failed to load profile</p>
                    <Button onClick={() => router.push('/')} className="mt-4">
                        Go Home
                    </Button>
                </div>
            </main>
        );
    }

    return (
        <main className="min-h-screen bg-gray-50 py-8">
            <div className="max-w-4xl mx-auto px-4">
                <div className="bg-white rounded-lg shadow-sm p-8">
                    <div className="flex items-center justify-between mb-8">
                        <h1 className="text-3xl font-bold text-gray-900">Settings</h1>
                        <Button onClick={() => router.push('/')} variant="outline">
                            Back to Chat
                        </Button>
                    </div>

                    <form onSubmit={handleSave} className="space-y-8">
                        {saveSuccess && <p className="text-green-600 text-sm">Profile updated successfully.</p>}
                        {saveError && <p className="text-red-600 text-sm">{saveError}</p>}
                        {/* Basic Information */}
                        <div>
                            <h2 className="text-xl font-semibold text-gray-900 mb-6">Basic Information</h2>
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
                                        <option value="en">English</option>
                                        <option value="es">Spanish</option>
                                        <option value="fr">French</option>
                                        <option value="de">German</option>
                                        <option value="it">Italian</option>
                                        <option value="pt">Portuguese</option>
                                        <option value="ja">Japanese</option>
                                        <option value="ko">Korean</option>
                                        <option value="zh">Chinese</option>
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
                                            { id: 'auto', label: 'Auto (Recommended)' },
                                            { id: 'gpt-4o', label: 'GPT-4o' },
                                            { id: 'llama3', label: 'LLaMA 3 (Local)' }
                                        ].map((model) => (
                                            <label key={model.id} className="flex items-center space-x-3">
                                                <input
                                                    type="radio"
                                                    name="preferred_model"
                                                    value={model.id}
                                                    checked={(profile.preferred_model || 'auto') === model.id}
                                                    onChange={(e) => handleChange('preferred_model', e.target.value)}
                                                    className="text-indigo-600 focus:ring-indigo-500"
                                                />
                                                <span className="text-gray-700">{model.label}</span>
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

                        <div className="flex justify-end pt-6">
                            <Button
                                type="submit"
                                disabled={saving}
                                className="bg-indigo-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-indigo-700 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50"
                            >
                                {saving ? 'Saving...' : 'Save Changes'}
                            </Button>
                        </div>
                    </form>
                </div>
            </div>
        </main>
    );
}

export default function SettingsPage() {
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
