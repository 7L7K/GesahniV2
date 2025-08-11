import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import OnboardingPage from '../page';

jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn(), replace: jest.fn() }) }));

jest.mock('@/lib/api', () => ({
  getOnboardingStatus: jest.fn(async () => ({ completed: true, steps: [], current_step: 0 })),
}));

describe('Onboarding Page', () => {
  test('renders loading state and then OnboardingFlow', async () => {
    render(<OnboardingPage />);
    expect(screen.getByText(/Loading/)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText(/Loading/)).not.toBeInTheDocument());
  });
});

import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import OnboardingFlow from '@/components/OnboardingFlow'

const stubStatus = {
  completed: false,
  steps: [
    { step: 'welcome', completed: false },
    { step: 'basic_info', completed: false },
    { step: 'device_prefs', completed: false },
    { step: 'preferences', completed: false },
    { step: 'integrations', completed: false },
    { step: 'complete', completed: false },
  ],
  current_step: 0,
}

describe('Onboarding UI basics', () => {
  it('renders and allows skipping steps', () => {
    const onComplete = jest.fn()
    render(<OnboardingFlow onboardingStatus={stubStatus as any} onComplete={onComplete} />)
    // Move past welcome to reveal skip button
    const startCta = screen.getByRole('button', { name: /get started/i })
    fireEvent.click(startCta)

    // Skip for now should be present after welcome step
    const skip = screen.getByText(/Skip for now/i)
    expect(skip).toBeInTheDocument()
    fireEvent.click(skip)
    // Should still render the flow with progress visible
    expect(screen.getByText(/Step/i)).toBeInTheDocument()
  })
})


