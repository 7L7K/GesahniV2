'use client';

import { useState } from 'react';
import { UserProfile } from '@/lib/api';

interface PreferencesStepProps {
    profile: Partial<UserProfile>;
    onNext: (data?: Partial<UserProfile>) => void;
    onBack: () => void;
    onSkip: () => void;
    loading: boolean;
    isFirstStep: boolean;
    isLastStep: boolean;
}

const COMMUNICATION_STYLES = [
    {
        id: 'casual',
        title: 'Casual & Friendly',
        description: 'Like talking to a helpful friend',
        icon: '😊'
    },
    {
        id: 'formal',
        title: 'Professional & Formal',
        description: 'Business-like and structured',
        icon: '👔'
    },
    {
        id: 'technical',
        title: 'Technical & Detailed',
        description: 'In-depth explanations with technical details',
        icon: '⚙️'
    }
];

const INTERESTS = [
    'Technology', 'Science', 'Music', 'Sports', 'Cooking', 'Travel',
    'Reading', 'Gaming', 'Fitness', 'Art', 'Photography', 'Finance',
    'Education', 'Health', 'Environment', 'Politics', 'Entertainment'
];

export default function PreferencesStep({ profile, onNext }: PreferencesStepProps) {
    const [formData, setFormData] = useState({
        communication_style: profile.communication_style || 'casual',
        interests: profile.interests || [],
        preferred_model: profile.preferred_model || 'auto',
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onNext(formData);
    };

    const handleInterestToggle = (interest: string) => {
        setFormData(prev => ({
            ...prev,
            interests: prev.interests?.includes(interest)
                ? prev.interests.filter(i => i !== interest)
                : [...(prev.interests || []), interest]
        }));
    };

    return (
        <div>
            <div className="text-center mb-8">
                <h2 className="text-2xl font-bold text-gray-900 mb-2">
                    Customize your experience
                </h2>
                <p className="text-gray-600">
                    Help us understand how you&apos;d like to interact with your AI assistant
                </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-8">
                {/* Communication Style */}
                <div>
                    <h3 className="text-lg font-medium text-gray-900 mb-4">
                        How would you like your AI to communicate with you?
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {COMMUNICATION_STYLES.map((style) => (
                            <label
                                key={style.id}
                                className={`relative cursor-pointer rounded-lg border-2 p-4 transition-all ${formData.communication_style === style.id
                                    ? 'border-indigo-500 bg-indigo-50'
                                    : 'border-gray-200 hover:border-gray-300'
                                    }`}
                            >
                                <input
                                    type="radio"
                                    name="communication_style"
                                    value={style.id}
                                    checked={formData.communication_style === style.id}
                                    onChange={(e) => setFormData(prev => ({ ...prev, communication_style: e.target.value }))}
                                    className="sr-only"
                                />
                                <div className="text-center">
                                    <div className="text-3xl mb-2">{style.icon}</div>
                                    <div className="font-medium text-gray-900">{style.title}</div>
                                    <div className="text-sm text-gray-600">{style.description}</div>
                                </div>
                            </label>
                        ))}
                    </div>
                </div>

                {/* Interests */}
                <div>
                    <h3 className="text-lg font-medium text-gray-900 mb-4">
                        What are your interests? (Select all that apply)
                    </h3>
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                        {INTERESTS.map((interest) => (
                            <label
                                key={interest}
                                className={`relative cursor-pointer rounded-lg border-2 p-3 text-center transition-all ${formData.interests?.includes(interest)
                                    ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                                    : 'border-gray-200 hover:border-gray-300'
                                    }`}
                            >
                                <input
                                    type="checkbox"
                                    checked={formData.interests?.includes(interest) || false}
                                    onChange={() => handleInterestToggle(interest)}
                                    className="sr-only"
                                />
                                <span className="text-sm font-medium">{interest}</span>
                            </label>
                        ))}
                    </div>
                </div>

                {/* Preferred Model */}
                <div>
                    <h3 className="text-lg font-medium text-gray-900 mb-4">
                        Which AI model would you prefer?
                    </h3>
                    <div className="space-y-3">
                        <label className="flex items-center space-x-3 cursor-pointer">
                            <input
                                type="radio"
                                name="preferred_model"
                                value="auto"
                                checked={formData.preferred_model === 'auto'}
                                onChange={(e) => setFormData(prev => ({ ...prev, preferred_model: e.target.value }))}
                                className="text-indigo-600 focus:ring-indigo-500"
                            />
                            <div>
                                <div className="font-medium text-gray-900">Auto (Recommended)</div>
                                <div className="text-sm text-gray-600">
                                    Let the system choose the best model for each task
                                </div>
                            </div>
                        </label>
                        <label className="flex items-center space-x-3 cursor-pointer">
                            <input
                                type="radio"
                                name="preferred_model"
                                value="gpt-4o"
                                checked={formData.preferred_model === 'gpt-4o'}
                                onChange={(e) => setFormData(prev => ({ ...prev, preferred_model: e.target.value }))}
                                className="text-indigo-600 focus:ring-indigo-500"
                            />
                            <div>
                                <div className="font-medium text-gray-900">GPT-4o</div>
                                <div className="text-sm text-gray-600">
                                    Best for complex reasoning and creative tasks
                                </div>
                            </div>
                        </label>
                        <label className="flex items-center space-x-3 cursor-pointer">
                            <input
                                type="radio"
                                name="preferred_model"
                                value="llama3"
                                checked={formData.preferred_model === 'llama3'}
                                onChange={(e) => setFormData(prev => ({ ...prev, preferred_model: e.target.value }))}
                                className="text-indigo-600 focus:ring-indigo-500"
                            />
                            <div>
                                <div className="font-medium text-gray-900">LLaMA 3 (Local)</div>
                                <div className="text-sm text-gray-600">
                                    Fast, private, and runs on your local machine
                                </div>
                            </div>
                        </label>
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
