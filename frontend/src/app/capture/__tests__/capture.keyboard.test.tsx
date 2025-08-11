import React from 'react'
import { render, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import CaptureMode from '@/components/CaptureMode'

jest.mock('next/navigation', () => ({ useRouter: () => ({ replace: jest.fn() }) }))

describe('Capture keyboard', () => {
  it('Space key handler attaches without crashing', () => {
    const { unmount } = render(<CaptureMode />)
    fireEvent.keyDown(window, { code: 'Space' })
    unmount()
  })
})


