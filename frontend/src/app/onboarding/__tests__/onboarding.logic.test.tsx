import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import OnboardingFlow from '@/components/OnboardingFlow'
import * as api from '@/lib/api'

jest.mock('@/lib/api')

const mockUpdateProfile = api.updateProfile as jest.Mock
const mockCompleteOnboarding = api.completeOnboarding as jest.Mock

function makeStatus(partial?: Partial<api.OnboardingStatus>): api.OnboardingStatus {
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
    current_step: 0,
    ...(partial || {}),
  }
}

describe('OnboardingFlow logic', () => {
  beforeEach(() => {
    jest.resetAllMocks()
  })

  it('defaults to step 0 when no status', () => {
    render(<OnboardingFlow onboardingStatus={null} onComplete={jest.fn()} />)
    expect(screen.getByText(/Step 1 of/i)).toBeInTheDocument()
  })

  it('uses explicit current_step when valid', () => {
    render(<OnboardingFlow onboardingStatus={makeStatus({ current_step: 3 })} onComplete={jest.fn()} />)
    expect(screen.getByText(/Step 4 of/i)).toBeInTheDocument()
  })

  it('falls back to first incomplete step when current_step invalid', () => {
    render(<OnboardingFlow onboardingStatus={makeStatus({ current_step: 999, steps: [
      { step: 'welcome', completed: true },
      { step: 'basic_info', completed: false },
      { step: 'device_prefs', completed: false },
      { step: 'preferences', completed: false },
      { step: 'integrations', completed: false },
      { step: 'complete', completed: false },
    ] })} onComplete={jest.fn()} />)
    expect(screen.getByText(/Step 2 of/i)).toBeInTheDocument()
  })

  it('incremental next without data advances step without persisting', async () => {
    render(<OnboardingFlow onboardingStatus={makeStatus()} onComplete={jest.fn()} />)
    // Welcome step -> click primary CTA
    fireEvent.click(screen.getByRole('button', { name: /let's get started/i }))
    // Basic info now visible (has Continue button)
    expect(screen.getByRole('button', { name: /continue/i })).toBeInTheDocument()
    expect(mockUpdateProfile).not.toHaveBeenCalled()
  })

  it('saving step data calls updateProfile', async () => {
    render(<OnboardingFlow onboardingStatus={makeStatus()} onComplete={jest.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /let's get started/i }))

    // Fill name on BasicInfoStep
    fireEvent.change(screen.getByLabelText(/Full Name/i), { target: { value: 'Ada Lovelace' } })
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))

    await waitFor(() => expect(mockUpdateProfile).toHaveBeenCalled())
  })

  it('skip button advances without saving', async () => {
    render(<OnboardingFlow onboardingStatus={makeStatus()} onComplete={jest.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    fireEvent.click(screen.getByText(/Skip for now/i))
    expect(mockUpdateProfile).not.toHaveBeenCalled()
  })

  it('final step calls completeOnboarding and onComplete', async () => {
    const onComplete = jest.fn()
    render(<OnboardingFlow onboardingStatus={makeStatus({ current_step: 5 })} onComplete={onComplete} />)
    fireEvent.click(screen.getByRole('button', { name: /start using/i }))
    await waitFor(() => expect(mockCompleteOnboarding).toHaveBeenCalled())
    expect(onComplete).toHaveBeenCalled()
  })

  it('progress bar shows correct percentage', () => {
    render(<OnboardingFlow onboardingStatus={makeStatus({ current_step: 2 })} onComplete={jest.fn()} />)
    expect(screen.getByText(/Step 3 of 6/)).toBeInTheDocument()
    expect(screen.getByText(/50%/i)).toBeInTheDocument()
  })

  it('skip advances the step indicator', () => {
    render(<OnboardingFlow onboardingStatus={makeStatus({ current_step: 1 })} onComplete={jest.fn()} />)
    // On step 2 of 6
    expect(screen.getByText(/Step 2 of 6/)).toBeInTheDocument()
    // Skip
    const skip = screen.getByText(/Skip for now/i)
    fireEvent.click(skip)
    expect(screen.getByText(/Step 3 of 6/)).toBeInTheDocument()
  })

  it('merges data across steps and persists latest profile', async () => {
    render(<OnboardingFlow onboardingStatus={makeStatus()} onComplete={jest.fn()} />)
    // Welcome -> next
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    // Basic info set name
    fireEvent.change(screen.getByLabelText(/Full Name/i), { target: { value: 'Alan Turing' } })
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))
    // Device prefs -> continue (defaults)
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))
    // Preferences -> choose Technical and continue
    fireEvent.click(screen.getByLabelText(/Technical & Detailed/i))
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))
    await waitFor(() => expect((mockUpdateProfile.mock.calls.at(-1)?.[0] || {})).toEqual(expect.objectContaining({ name: 'Alan Turing', communication_style: 'technical' })))
  })

  it('handles updateProfile error gracefully mid-flow', async () => {
    mockUpdateProfile.mockRejectedValueOnce(new Error('network'))
    render(<OnboardingFlow onboardingStatus={makeStatus()} onComplete={jest.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /get started/i }))
    fireEvent.change(screen.getByLabelText(/Full Name/i), { target: { value: 'Linus Torvalds' } })
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))
    // Should still move to next step even if save failed
    await waitFor(() => expect(screen.getByText(/Step 3 of 6/)).toBeInTheDocument())
  })

  it('final step persists profile then completes', async () => {
    const onComplete = jest.fn()
    render(<OnboardingFlow onboardingStatus={makeStatus({ current_step: 5 })} onComplete={onComplete} />)
    fireEvent.click(screen.getByRole('button'))
    await waitFor(() => expect(mockUpdateProfile).toHaveBeenCalled())
    await waitFor(() => expect(mockCompleteOnboarding).toHaveBeenCalled())
    expect(onComplete).toHaveBeenCalled()
  })
})


