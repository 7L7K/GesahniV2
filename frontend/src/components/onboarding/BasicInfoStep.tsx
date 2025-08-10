'use client';

import { useState } from 'react';
import { UserProfile } from '@/lib/api';

interface BasicInfoStepProps {
    profile: Partial<UserProfile>;
    onNext: (data?: Partial<UserProfile>) => void;
    onBack: () => void;
    onSkip: () => void;
    loading: boolean;
    isFirstStep: boolean;
    isLastStep: boolean;
}

export default function BasicInfoStep({ profile, onNext }: BasicInfoStepProps) {
    const [formData, setFormData] = useState({
        name: profile.name || '',
        email: profile.email || '',
        timezone: profile.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
        language: profile.language || 'en',
        occupation: profile.occupation || '',
        home_location: profile.home_location || '',
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onNext(formData);
    };

    const handleChange = (field: string, value: string) => {
        setFormData(prev => ({ ...prev, [field]: value }));
    };

    return (
        <div>
            <div className="text-center mb-8">
                <h2 className="text-2xl font-bold text-gray-900 mb-2">
                    Tell us about yourself
                </h2>
                <p className="text-gray-600">
                    This helps us personalize your AI assistant experience
                </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                        <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2">
                            Full Name *
                        </label>
                        <input
                            type="text"
                            id="name"
                            value={formData.name}
                            onChange={(e) => handleChange('name', e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                            placeholder="Enter your full name"
                            required
                        />
                    </div>

                    <div>
                        <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
                            Email Address
                        </label>
                        <input
                            type="email"
                            id="email"
                            value={formData.email}
                            onChange={(e) => handleChange('email', e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                            placeholder="your.email@example.com"
                        />
                    </div>

                    <div>
                        <label htmlFor="timezone" className="block text-sm font-medium text-gray-700 mb-2">
                            Timezone
                        </label>
                        <select
                            id="timezone"
                            value={formData.timezone}
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
                            value={formData.language}
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

                    <div>
                        <label htmlFor="occupation" className="block text-sm font-medium text-gray-700 mb-2">
                            Occupation
                        </label>
                        <input
                            type="text"
                            id="occupation"
                            value={formData.occupation}
                            onChange={(e) => handleChange('occupation', e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                            placeholder="e.g., Software Engineer, Teacher, etc."
                        />
                    </div>

                    <div>
                        <label htmlFor="home_location" className="block text-sm font-medium text-gray-700 mb-2">
                            Home Location
                        </label>
                        <input
                            type="text"
                            id="home_location"
                            value={formData.home_location}
                            onChange={(e) => handleChange('home_location', e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                            placeholder="e.g., New York, NY"
                        />
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
