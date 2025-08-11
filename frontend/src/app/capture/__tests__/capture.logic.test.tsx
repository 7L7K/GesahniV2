import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import CaptureMode from '@/components/CaptureMode'

jest.mock('next/navigation', () => ({ useRouter: () => ({ replace: jest.fn() }) }))

describe('Capture logic smoke', () => {
  it('renders header and buttons', () => {
    render(<CaptureMode />)
    expect(screen.getByText(/Gesahni Capture/i)).toBeInTheDocument()
    expect(screen.getByText(/New Session/i)).toBeInTheDocument()
    expect(screen.getAllByText(/Reset/i).length).toBeGreaterThan(0)
  })
})


