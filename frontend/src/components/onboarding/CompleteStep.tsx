'use client';

import { UserProfile } from '@/lib/api';

interface CompleteStepProps {
    profile: Partial<UserProfile>;
    onNext: (data?: Partial<UserProfile>) => void;
    onBack: () => void;
    onSkip: () => void;
    loading: boolean;
    isFirstStep: boolean;
    isLastStep: boolean;
}

export default function CompleteStep({ profile, onNext, loading }: CompleteStepProps) {
    return (
        <div className="text-center">
            <div className="mb-8">
                <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-6">
                    <svg className="w-10 h-10 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                </div>
                <h1 className="text-3xl font-bold text-gray-900 mb-4">
                    You&apos;re all set! 🎉
                </h1>
                <p className="text-lg text-gray-600 mb-6">
                    Your AI assistant is now personalized and ready to help you.
                    You can always update your preferences later in the settings.
                </p>
            </div>

            {/* Summary */}
            <div className="bg-gray-50 rounded-lg p-6 mb-8">
                <h3 className="text-lg font-medium text-gray-900 mb-4">
                    Here&apos;s what we&apos;ve set up for you:
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-left">
                    {profile.name && (
                        <div className="flex items-center space-x-3">
                            <div className="w-6 h-6 bg-indigo-100 rounded-full flex items-center justify-center">
                                <svg className="w-3 h-3 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                                </svg>
                            </div>
                            <span className="text-gray-700">Personalized for {profile.name}</span>
                        </div>
                    )}
                    {profile.communication_style && (
                        <div className="flex items-center space-x-3">
                            <div className="w-6 h-6 bg-indigo-100 rounded-full flex items-center justify-center">
                                <svg className="w-3 h-3 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                                </svg>
                            </div>
                            <span className="text-gray-700">{profile.communication_style} communication style</span>
                        </div>
                    )}
                    {profile.preferred_model && (
                        <div className="flex items-center space-x-3">
                            <div className="w-6 h-6 bg-indigo-100 rounded-full flex items-center justify-center">
                                <svg className="w-3 h-3 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                                </svg>
                            </div>
                            <span className="text-gray-700">{profile.preferred_model} AI model</span>
                        </div>
                    )}
                    {(profile.calendar_integration || profile.gmail_integration) && (
                        <div className="flex items-center space-x-3">
                            <div className="w-6 h-6 bg-indigo-100 rounded-full flex items-center justify-center">
                                <svg className="w-3 h-3 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                                </svg>
                            </div>
                            <span className="text-gray-700">
                                {profile.calendar_integration && profile.gmail_integration
                                    ? 'Calendar & Gmail connected'
                                    : profile.calendar_integration
                                        ? 'Calendar connected'
                                        : 'Gmail connected'
                                }
                            </span>
                        </div>
                    )}
                </div>
            </div>

            {/* Getting Started Tips */}
            <div className="bg-blue-50 rounded-lg p-6 mb-8">
                <h3 className="text-lg font-medium text-blue-900 mb-4">
                    🚀 Getting Started Tips
                </h3>
                <div className="space-y-3 text-left">
                    <div className="flex items-start space-x-3">
                        <div className="w-2 h-2 bg-blue-600 rounded-full mt-2 flex-shrink-0"></div>
                        <div>
                            <div className="font-medium text-blue-900">Try asking about your day</div>
                            <div className="text-sm text-blue-700">&quot;What&apos;s on my calendar today?&quot; or &quot;Summarize my emails&quot;</div>
                        </div>
                    </div>
                    <div className="flex items-start space-x-3">
                        <div className="w-2 h-2 bg-blue-600 rounded-full mt-2 flex-shrink-0"></div>
                        <div>
                            <div className="font-medium text-blue-900">Control your smart home</div>
                            <div className="text-sm text-blue-700">&quot;Turn on the living room lights&quot; or &quot;Set thermostat to 72°&quot;</div>
                        </div>
                    </div>
                    <div className="flex items-start space-x-3">
                        <div className="w-2 h-2 bg-blue-600 rounded-full mt-2 flex-shrink-0"></div>
                        <div>
                            <div className="font-medium text-blue-900">Get help with tasks</div>
                            <div className="text-sm text-blue-700">&quot;Help me write an email&quot; or &quot;What&apos;s the weather like?&quot;</div>
                        </div>
                    </div>
                </div>
            </div>

            <button
                onClick={() => onNext()}
                disabled={loading}
                className="w-full bg-indigo-600 text-white py-3 px-6 rounded-lg font-medium hover:bg-indigo-700 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50"
            >
                {loading ? (
                    <div className="flex items-center justify-center space-x-2">
                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                        <span>Setting up your experience...</span>
                    </div>
                ) : (
                    'Start using GesahniV2! 🦙✨'
                )}
            </button>
        </div>
    );
}
