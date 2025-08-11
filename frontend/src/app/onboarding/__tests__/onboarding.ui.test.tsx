import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import OnboardingFlow from '@/components/OnboardingFlow'

const stubStatus = {
    completed: false,
    steps: [
        { id: 'welcome', completed: false },
        { id: 'basic_info', completed: false },
        { id: 'preferences', completed: false },
        { id: 'integrations', completed: false },
        { id: 'complete', completed: false },
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


