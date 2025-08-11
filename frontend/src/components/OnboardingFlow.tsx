'use client';

import { useState, useEffect } from 'react';
import { OnboardingStatus, UserProfile, updateProfile, completeOnboarding } from '@/lib/api';
import WelcomeStep from './onboarding/WelcomeStep';
import BasicInfoStep from './onboarding/BasicInfoStep';
import PreferencesStep from './onboarding/PreferencesStep';
import IntegrationsStep from './onboarding/IntegrationsStep';
import CompleteStep from './onboarding/CompleteStep';
import DevicePrefsStep from './onboarding/DevicePrefsStep';

interface OnboardingFlowProps {
    onboardingStatus: OnboardingStatus | null;
    onComplete: () => void;
}

const STEPS = [
    { id: 'welcome', component: WelcomeStep },
    { id: 'basic_info', component: BasicInfoStep },
    { id: 'device_prefs', component: DevicePrefsStep },
    { id: 'preferences', component: PreferencesStep },
    { id: 'integrations', component: IntegrationsStep },
    { id: 'complete', component: CompleteStep },
];

export default function OnboardingFlow({ onboardingStatus, onComplete }: OnboardingFlowProps) {
    const [currentStepIndex, setCurrentStepIndex] = useState(0);
    const [profile, setProfile] = useState<Partial<UserProfile>>({});
    const [loading, setLoading] = useState(false);
    // Note: we intentionally avoid fetching profile here to keep this component
    // framework-agnostic for tests (no QueryClientProvider requirement).

    useEffect(() => {
        if (!onboardingStatus) {
            setCurrentStepIndex(0);
            return;
        }
        const explicit = Number(onboardingStatus.current_step);
        if (!Number.isNaN(explicit) && explicit >= 0 && explicit < STEPS.length) {
            setCurrentStepIndex(explicit);
            return;
        }
        const firstIncompleteIndex = onboardingStatus.steps.findIndex(step => !step.completed);
        setCurrentStepIndex(firstIncompleteIndex >= 0 ? firstIncompleteIndex : 0);
    }, [onboardingStatus]);

    const handleNext = async (stepData?: Partial<UserProfile>) => {
        const nextProfile = stepData ? { ...profile, ...stepData } : { ...profile };
        setProfile(nextProfile);

        // Persist incremental progress when data provided
        try {
            if (stepData && Object.keys(stepData).length > 0) {
                await updateProfile(nextProfile);
            }
        } catch (err) {
            console.error('Failed to save step data:', err);
        }

        if (currentStepIndex < STEPS.length - 1) {
            setCurrentStepIndex(prev => prev + 1);
            return;
        }

        // Complete onboarding on final step
        setLoading(true);
        try {
            await updateProfile(nextProfile);
            await completeOnboarding();
            onComplete();
        } catch (error) {
            console.error('Failed to complete onboarding:', error);
            setLoading(false);
        }
    };

    const handleBack = () => {
        if (currentStepIndex > 0) {
            setCurrentStepIndex(prev => prev - 1);
        }
    };

    const handleSkip = () => {
        handleNext();
    };

    const currentStep = STEPS[currentStepIndex];
    const StepComponent = currentStep.component;

    return (
        <div className="min-h-screen flex items-center justify-center p-4">
            <div className="w-full max-w-2xl">
                {/* Progress Bar */}
                <div className="mb-8">
                    <div className="flex justify-between items-center mb-2">
                        <span className="text-sm font-medium text-gray-600">
                            Step {currentStepIndex + 1} of {STEPS.length}
                        </span>
                        <span className="text-sm text-gray-500">
                            {Math.round(((currentStepIndex + 1) / STEPS.length) * 100)}% Complete
                        </span>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-2">
                        <div
                            className="bg-indigo-600 h-2 rounded-full transition-all duration-300"
                            style={{ width: `${((currentStepIndex + 1) / STEPS.length) * 100}%` }}
                        ></div>
                    </div>
                </div>

                {/* Step Content */}
                <div className="bg-white rounded-xl shadow-lg p-8">
                    <StepComponent
                        profile={profile}
                        onNext={handleNext}
                        onBack={handleBack}
                        onSkip={handleSkip}
                        loading={loading}
                        isFirstStep={currentStepIndex === 0}
                        isLastStep={currentStepIndex === STEPS.length - 1}
                    />
                </div>

                {/* Navigation */}
                {!currentStep.id.includes('welcome') && !currentStep.id.includes('complete') && (
                    <div className="mt-6 flex justify-between">
                        <button
                            onClick={handleBack}
                            className="px-6 py-2 text-gray-600 hover:text-gray-800 transition-colors"
                            disabled={loading}
                        >
                            ← Back
                        </button>
                        <button
                            onClick={handleSkip}
                            className="px-6 py-2 text-gray-500 hover:text-gray-700 transition-colors"
                            disabled={loading}
                        >
                            Skip for now
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}
