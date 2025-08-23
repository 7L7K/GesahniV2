import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import OnboardingFlow from '@/components/OnboardingFlow'

function makeStatus(current_step = 0) {
  return {
    completed: false,
    steps: [
      { step: 'welcome', completed: false },
      { step: 'basic_info', completed: false },
      { step: 'device_prefs', completed: false },
      { step: 'preferences', completed: false },
      { step: 'integrations', completed: false },
      { step: 'complete', completed: false },
    ],
    current_step,
  }
}

describe('Onboarding navigation controls', () => {
  it('no Back/Skip on welcome step', () => {
    render(<OnboardingFlow onboardingStatus={makeStatus(0) as any} onComplete={() => {}} />)
    expect(screen.queryByText(/Back/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Skip for now/i)).not.toBeInTheDocument()
  })

  it('Back/Skip appear on middle steps', () => {
    render(<OnboardingFlow onboardingStatus={makeStatus(1) as any} onComplete={() => {}} />)
    expect(screen.getByText(/Back/i)).toBeInTheDocument()
    expect(screen.getByText(/Skip for now/i)).toBeInTheDocument()
  })

  it('Back decreases step number', () => {
    render(<OnboardingFlow onboardingStatus={makeStatus(2) as any} onComplete={() => {}} />)
    expect(screen.getByText(/Step 3 of/i)).toBeInTheDocument()
    fireEvent.click(screen.getByText(/Back/i))
    expect(screen.getByText(/Step 2 of/i)).toBeInTheDocument()
  })
})
