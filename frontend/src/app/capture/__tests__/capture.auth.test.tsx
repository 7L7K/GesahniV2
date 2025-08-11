import React from 'react'
import { render } from '@testing-library/react'
import '@testing-library/jest-dom'
import CaptureMode from '@/components/CaptureMode'

const replace = jest.fn()
jest.mock('next/navigation', () => ({ useRouter: () => ({ replace }) }))

describe('Capture auth guard', () => {
  beforeEach(() => {
    replace.mockReset()
    // simulate logged out
    const store: Record<string, string> = {}
    Object.defineProperty(window, 'localStorage', { value: {
      getItem: (k: string) => store[k] || null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: (i: number) => Object.keys(store)[i] || null,
      length: 0,
    }, configurable: true })
  })

  it('redirects when token missing', () => {
    render(<CaptureMode />)
    expect(replace).toHaveBeenCalled()
  })
})


