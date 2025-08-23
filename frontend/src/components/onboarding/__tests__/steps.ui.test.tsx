import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import BasicInfoStep from '@/components/onboarding/BasicInfoStep'
import PreferencesStep from '@/components/onboarding/PreferencesStep'
import DevicePrefsStep from '@/components/onboarding/DevicePrefsStep'
import CompleteStep from '@/components/onboarding/CompleteStep'

describe('Onboarding step components', () => {
  it('BasicInfoStep captures name and continues', () => {
    const onNext = jest.fn()
    render(<BasicInfoStep profile={{}} onNext={onNext} onBack={() => { }} onSkip={() => { }} loading={false} isFirstStep isLastStep={false} /> as any)
    fireEvent.change(screen.getByLabelText(/Full Name/i), { target: { value: 'Grace Hopper' } })
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))
    expect(onNext).toHaveBeenCalled()
  })

  it('PreferencesStep toggles interests', () => {
    const onNext = jest.fn()
    render(<PreferencesStep profile={{}} onNext={onNext} onBack={() => { }} onSkip={() => { }} loading={false} isFirstStep={false} isLastStep={false} /> as any)
    const interest = screen.getByText('Music')
    fireEvent.click(interest)
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))
    expect(onNext).toHaveBeenCalled()
  })

  it('DevicePrefsStep updates ranges and continues', () => {
    const onNext = jest.fn()
    render(<DevicePrefsStep profile={{}} onNext={onNext} onBack={() => { }} onSkip={() => { }} loading={false} isFirstStep={false} isLastStep={false} /> as any)
    fireEvent.change(screen.getByRole('slider', { name: /speech pace/i }), { target: { value: '1.1' } })
    fireEvent.click(screen.getByRole('button', { name: /continue/i }))
    expect(onNext).toHaveBeenCalled()
  })

  it('CompleteStep primary button calls onNext', () => {
    const onNext = jest.fn()
    render(<CompleteStep profile={{ name: 'A' }} onNext={onNext} onBack={() => { }} onSkip={() => { }} loading={false} isFirstStep={false} isLastStep /> as any)
    fireEvent.click(screen.getByRole('button'))
    expect(onNext).toHaveBeenCalled()
  })
})
