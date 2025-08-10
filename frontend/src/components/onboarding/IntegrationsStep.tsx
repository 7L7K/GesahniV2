'use client';

import { useState } from 'react';
import { UserProfile } from '@/lib/api';

interface IntegrationsStepProps {
    profile: Partial<UserProfile>;
    onNext: (data?: Partial<UserProfile>) => void;
    onBack: () => void;
    onSkip: () => void;
    loading: boolean;
    isFirstStep: boolean;
    isLastStep: boolean;
}

export default function IntegrationsStep({ profile, onNext }: IntegrationsStepProps) {
    const [formData, setFormData] = useState({
        calendar_integration: profile.calendar_integration || false,
        gmail_integration: profile.gmail_integration || false,
    });

    const [connecting, setConnecting] = useState<string | null>(null);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onNext(formData);
    };

    const handleConnect = async (service: 'calendar' | 'gmail') => {
        setConnecting(service);

        // Simulate connection process
        setTimeout(() => {
            setFormData(prev => ({
                ...prev,
                [`${service}_integration`]: true
            }));
            setConnecting(null);
        }, 2000);
    };

    const handleDisconnect = (service: 'calendar' | 'gmail') => {
        setFormData(prev => ({
            ...prev,
            [`${service}_integration`]: false
        }));
    };

    return (
        <div>
            <div className="text-center mb-8">
                <h2 className="text-2xl font-bold text-gray-900 mb-2">
                    Connect your services
                </h2>
                <p className="text-gray-600">
                    Connect your accounts to enable powerful features like calendar management and email assistance
                </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
                {/* Gmail Integration */}
                <div className="border border-gray-200 rounded-lg p-6">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-4">
                            <div className="w-12 h-12 bg-red-100 rounded-lg flex items-center justify-center">
                                <svg className="w-6 h-6 text-red-600" fill="currentColor" viewBox="0 0 24 24">
                                    <path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z" />
                                </svg>
                            </div>
                            <div>
                                <h3 className="text-lg font-medium text-gray-900">Gmail</h3>
                                <p className="text-sm text-gray-600">
                                    Read and compose emails, manage your inbox
                                </p>
                            </div>
                        </div>
                        <div>
                            {formData.gmail_integration ? (
                                <div className="flex items-center space-x-3">
                                    <span className="text-sm text-green-600 font-medium">Connected</span>
                                    <button
                                        type="button"
                                        onClick={() => handleDisconnect('gmail')}
                                        className="text-sm text-red-600 hover:text-red-700"
                                    >
                                        Disconnect
                                    </button>
                                </div>
                            ) : (
                                <button
                                    type="button"
                                    onClick={() => handleConnect('gmail')}
                                    disabled={connecting === 'gmail'}
                                    className="bg-red-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-50"
                                >
                                    {connecting === 'gmail' ? (
                                        <div className="flex items-center space-x-2">
                                            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                                            <span>Connecting...</span>
                                        </div>
                                    ) : (
                                        'Connect Gmail'
                                    )}
                                </button>
                            )}
                        </div>
                    </div>
                </div>

                {/* Calendar Integration */}
                <div className="border border-gray-200 rounded-lg p-6">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-4">
                            <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center">
                                <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                </svg>
                            </div>
                            <div>
                                <h3 className="text-lg font-medium text-gray-900">Google Calendar</h3>
                                <p className="text-sm text-gray-600">
                                    Schedule meetings, check availability, manage events
                                </p>
                            </div>
                        </div>
                        <div>
                            {formData.calendar_integration ? (
                                <div className="flex items-center space-x-3">
                                    <span className="text-sm text-green-600 font-medium">Connected</span>
                                    <button
                                        type="button"
                                        onClick={() => handleDisconnect('calendar')}
                                        className="text-sm text-red-600 hover:text-red-700"
                                    >
                                        Disconnect
                                    </button>
                                </div>
                            ) : (
                                <button
                                    type="button"
                                    onClick={() => handleConnect('calendar')}
                                    disabled={connecting === 'calendar'}
                                    className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
                                >
                                    {connecting === 'calendar' ? (
                                        <div className="flex items-center space-x-2">
                                            <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                                            <span>Connecting...</span>
                                        </div>
                                    ) : (
                                        'Connect Calendar'
                                    )}
                                </button>
                            )}
                        </div>
                    </div>
                </div>

                {/* Benefits */}
                <div className="bg-gray-50 rounded-lg p-6">
                    <h3 className="text-lg font-medium text-gray-900 mb-4">
                        What you can do with these integrations:
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="flex items-start space-x-3">
                            <div className="w-6 h-6 bg-green-100 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                                <svg className="w-3 h-3 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                </svg>
                            </div>
                            <div>
                                <div className="font-medium text-gray-900">Email Management</div>
                                <div className="text-sm text-gray-600">Draft emails, summarize conversations, and manage your inbox</div>
                            </div>
                        </div>
                        <div className="flex items-start space-x-3">
                            <div className="w-6 h-6 bg-green-100 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                                <svg className="w-3 h-3 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                </svg>
                            </div>
                            <div>
                                <div className="font-medium text-gray-900">Smart Scheduling</div>
                                <div className="text-sm text-gray-600">Find meeting times, create events, and manage your calendar</div>
                            </div>
                        </div>
                        <div className="flex items-start space-x-3">
                            <div className="w-6 h-6 bg-green-100 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                                <svg className="w-3 h-3 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                </svg>
                            </div>
                            <div>
                                <div className="font-medium text-gray-900">Context Awareness</div>
                                <div className="text-sm text-gray-600">Your AI will know about your schedule and commitments</div>
                            </div>
                        </div>
                        <div className="flex items-start space-x-3">
                            <div className="w-6 h-6 bg-green-100 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                                <svg className="w-3 h-3 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                </svg>
                            </div>
                            <div>
                                <div className="font-medium text-gray-900">Proactive Assistance</div>
                                <div className="text-sm text-gray-600">Get reminders and suggestions based on your data</div>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="flex justify-end pt-6">
                    <button
                        type="submit"
                        className="bg-indigo-600 text-white py-2 px-6 rounded-lg font-medium hover:bg-indigo-700 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
                    >
                        Continue →
                    </button>
                </div>
            </form>
        </div>
    );
}
