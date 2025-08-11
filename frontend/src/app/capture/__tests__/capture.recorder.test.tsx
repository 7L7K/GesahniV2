import React from 'react'
import { render, screen, fireEvent, act } from '@testing-library/react'
import '@testing-library/jest-dom'
import CaptureMode from '@/components/CaptureMode'
import * as api from '@/lib/api'

jest.mock('next/navigation', () => ({ useRouter: () => ({ replace: jest.fn() }) }))
jest.mock('@/lib/api')

describe('Capture recorder controls', () => {
  it('buttons exist and can be clicked', async () => {
    ;(api.apiFetch as jest.Mock).mockResolvedValue(new Response(JSON.stringify({ session_id: 'sid' }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    render(<CaptureMode />)
    // Start/stop via space
    await act(async () => { fireEvent.keyDown(window, { code: 'Space' }) })
    const pause = await screen.findByText(/Pause/i)
    fireEvent.click(pause)
    const newSession = screen.getByText(/New Session/i)
    fireEvent.click(newSession)
    const reset = screen.getByText(/Reset/i)
    fireEvent.click(reset)
  })
})


