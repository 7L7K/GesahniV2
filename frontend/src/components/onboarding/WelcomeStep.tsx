'use client';

import { UserProfile } from '@/lib/api';

interface WelcomeStepProps {
    profile: Partial<UserProfile>;
    onNext: (data?: Partial<UserProfile>) => void;
    onBack: () => void;
    onSkip: () => void;
    loading: boolean;
    isFirstStep: boolean;
    isLastStep: boolean;
}

export default function WelcomeStep({ onNext }: WelcomeStepProps) {
    return (
        <div className="text-center">
            <div className="mb-8">
                <div className="w-20 h-20 bg-indigo-100 rounded-full flex items-center justify-center mx-auto mb-6">
                    <svg className="w-10 h-10 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                    </svg>
                </div>
                <h1 className="text-3xl font-bold text-gray-900 mb-4">
                    Welcome to GesahniV2! 🦙✨
                </h1>
                <p className="text-lg text-gray-600 mb-6">
                    Your AI assistant is ready to help you control your smart home and answer questions.
                    Let&apos;s get to know you better to personalize your experience.
                </p>
            </div>

            <div className="space-y-4 mb-8">
                <div className="flex items-center justify-center space-x-3">
                    <div className="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center">
                        <svg className="w-4 h-4 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                    </div>
                    <span className="text-gray-700">Smart home control with Home Assistant</span>
                </div>
                <div className="flex items-center justify-center space-x-3">
                    <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
                        <svg className="w-4 h-4 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                    </div>
                    <span className="text-gray-700">Local LLaMA 3 for fast responses</span>
                </div>
                <div className="flex items-center justify-center space-x-3">
                    <div className="w-8 h-8 bg-purple-100 rounded-full flex items-center justify-center">
                        <svg className="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                    </div>
                    <span className="text-gray-700">GPT-4o for complex tasks</span>
                </div>
                <div className="flex items-center justify-center space-x-3">
                    <div className="w-8 h-8 bg-orange-100 rounded-full flex items-center justify-center">
                        <svg className="w-4 h-4 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                    </div>
                    <span className="text-gray-700">Calendar and email integration</span>
                </div>
            </div>

            <button
                onClick={() => onNext()}
                className="w-full bg-indigo-600 text-white py-3 px-6 rounded-lg font-medium hover:bg-indigo-700 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
            >
                Let&apos;s get started! →
            </button>
        </div>
    );
}
