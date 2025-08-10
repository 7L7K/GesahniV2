'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getOnboardingStatus, OnboardingStatus } from '@/lib/api';
import OnboardingFlow from '@/components/OnboardingFlow';

function OnboardingPageInner() {
    const [onboardingStatus, setOnboardingStatus] = useState<OnboardingStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const router = useRouter();

    useEffect(() => {
        const checkOnboardingStatus = async () => {
            try {
                const status = await getOnboardingStatus();
                setOnboardingStatus(status);

                // If onboarding is already completed, redirect to main app
                if (status.completed) {
                    router.replace('/');
                }
            } catch (error) {
                console.error('Failed to get onboarding status:', error);
                // If there's an error, assume we need to start onboarding
                setOnboardingStatus({
                    completed: false,
                    steps: [],
                    current_step: 0
                });
            } finally {
                setLoading(false);
            }
        };

        checkOnboardingStatus();
    }, [router]);

    if (loading) {
        return (
            <main className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
                    <p className="text-gray-600">Loading onboarding...</p>
                </div>
            </main>
        );
    }

    return (
        <main className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
            <OnboardingFlow
                onboardingStatus={onboardingStatus}
                onComplete={() => router.replace('/')}
            />
        </main>
    );
}

export default function OnboardingPage() {
    return (
        <Suspense fallback={
            <main className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
                    <p className="text-gray-600">Loading...</p>
                </div>
            </main>
        }>
            <OnboardingPageInner />
        </Suspense>
    );
}
