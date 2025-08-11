import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import CaptureMode, { __TEST__CaptureInner as CaptureInner } from '@/components/CaptureMode'

jest.mock('next/navigation', () => ({ useRouter: () => ({ replace: jest.fn() }) }))
jest.mock('@/lib/api', () => ({ getToken: () => 'tok' }))

// Basic smoke tests for the capture UI using the provider; we will not open real media
describe('Capture UI', () => {
  it('renders within provider', () => {
    render(<CaptureMode />)
    expect(screen.getByText(/Gesahni Capture/i)).toBeInTheDocument()
  })

  it('shows hint text', () => {
    render(<CaptureMode />)
    expect(screen.getByText(/Press/i)).toBeInTheDocument()
  })
})


