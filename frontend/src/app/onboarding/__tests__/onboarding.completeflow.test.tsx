import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import OnboardingFlow from '@/components/OnboardingFlow'
import * as api from '@/lib/api'

jest.mock('@/lib/api')

describe('Onboarding end-to-end happy path', () => {
  beforeEach(() => jest.resetAllMocks())

  it('goes from welcome to complete and calls backend', async () => {
    const onComplete = jest.fn()
    const status = {
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
    render(<OnboardingFlow onboardingStatus={status as any} onComplete={onComplete} />)
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    fireEvent.change(screen.getByLabelText(/Full Name/i), { target: { value: 'Ada' } })
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))
    fireEvent.click(screen.getByRole('button', { name: /start using/i }))
    await waitFor(() => expect(api.completeOnboarding).toHaveBeenCalled())
    expect(onComplete).toHaveBeenCalled()
  })
})


