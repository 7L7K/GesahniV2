'use client';

import { useEffect, useState } from 'react';
import { UserProfile } from '@/lib/api';

interface DevicePrefsStepProps {
    profile: Partial<UserProfile>;
    onNext: (data?: Partial<UserProfile>) => void;
    onBack: () => void;
    onSkip: () => void;
    loading: boolean;
    isFirstStep: boolean;
    isLastStep: boolean;
}

export default function DevicePrefsStep({ profile, onNext }: DevicePrefsStepProps) {
    const [speechRate, setSpeechRate] = useState<number>(profile.speech_rate ?? 1.0);
    const [inputMode, setInputMode] = useState<'voice' | 'touch' | 'both'>(
        (profile.input_mode as any) ?? 'both',
    );
    const [fontScale, setFontScale] = useState<number>(profile.font_scale ?? 1.0);
    const [wakeWord, setWakeWord] = useState<boolean>(Boolean(profile.wake_word_enabled));

    // Immediate UX reflection: update document root font size so user sees effect
    useEffect(() => {
        const base = 16;
        document.documentElement.style.fontSize = `${Math.round(base * fontScale)}px`;
        return () => { document.documentElement.style.fontSize = ''; };
    }, [fontScale]);

    // Simple live TTS preview via SpeechSynthesis (browser-only, best-effort)
    const speakPreview = (text: string) => {
        try {
            if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;
            const u = new SpeechSynthesisUtterance(text);
            // Map 0.8..1.2 to speechSynthesis rate (0.1..10, default 1)
            u.rate = Math.max(0.1, Math.min(10, speechRate));
            window.speechSynthesis.cancel();
            window.speechSynthesis.speak(u);
        } catch { /* ignore */ }
    };

    const submit = (e: React.FormEvent) => {
        e.preventDefault();
        onNext({
            speech_rate: Number(speechRate || 1.0),
            input_mode: inputMode,
            font_scale: Number(fontScale || 1.0),
            wake_word_enabled: Boolean(wakeWord),
        });
    };

    return (
        <div>
            <div className="text-center mb-8">
                <h2 className="text-2xl font-bold text-gray-900 mb-2">Device preferences</h2>
                <p className="text-gray-600">We will apply changes immediately so you can feel the fit.</p>
            </div>

            <form onSubmit={submit} className="space-y-8">
                <div>
                    <h3 className="text-lg font-medium text-gray-900 mb-3">Speech pace</h3>
                    <div className="flex items-center gap-4">
                        <input
                            aria-label="Speech pace"
                            type="range"
                            min={0.8}
                            max={1.2}
                            step={0.05}
                            value={speechRate}
                            onChange={e => setSpeechRate(parseFloat(e.target.value))}
                            className="w-full"
                        />
                        <span className="w-16 text-sm text-gray-600 text-right">{speechRate.toFixed(2)}x</span>
                    </div>
                    <div className="mt-2">
                        <button
                            type="button"
                            className="text-sm text-indigo-600 hover:text-indigo-700"
                            onClick={() => speakPreview('This is your preview at the selected pace.')}
                        >
                            Preview voice
                        </button>
                    </div>
                </div>

                <div>
                    <h3 className="text-lg font-medium text-gray-900 mb-3">Input mode</h3>
                    <div className="flex flex-wrap gap-3">
                        {(['voice', 'touch', 'both'] as const).map(mode => (
                            <label key={mode} className={`cursor-pointer rounded-lg border px-4 py-2 text-sm ${inputMode === mode ? 'border-indigo-500 bg-indigo-50' : 'border-gray-200 hover:border-gray-300'}`}>
                                <input type="radio" name="input_mode" value={mode} className="sr-only" checked={inputMode === mode} onChange={() => setInputMode(mode)} />
                                {mode === 'voice' ? 'Voice only' : mode === 'touch' ? 'Touch only' : 'Voice + Touch'}
                            </label>
                        ))}
                    </div>
                </div>

                <div>
                    <h3 className="text-lg font-medium text-gray-900 mb-3">Font size</h3>
                    <div className="flex items-center gap-4">
                        <input
                            aria-label="Font size"
                            type="range"
                            min={0.9}
                            max={1.4}
                            step={0.05}
                            value={fontScale}
                            onChange={e => setFontScale(parseFloat(e.target.value))}
                            className="w-full"
                        />
                        <span className="w-16 text-sm text-gray-600 text-right">{Math.round(fontScale * 100)}%</span>
                    </div>
                </div>

                <div>
                    <h3 className="text-lg font-medium text-gray-900 mb-3">Wake word</h3>
                    <label className="inline-flex items-center gap-3">
                        <input type="checkbox" checked={wakeWord} onChange={e => setWakeWord(e.target.checked)} />
                        <span className="text-sm text-gray-700">Enable "Hey Sweetie"</span>
                    </label>
                </div>

                <div className="flex justify-end pt-4">
                    <button type="submit" className="bg-indigo-600 text-white py-2 px-6 rounded-lg font-medium hover:bg-indigo-700 transition-colors">Continue →</button>
                </div>
            </form>
        </div>
    );
}
