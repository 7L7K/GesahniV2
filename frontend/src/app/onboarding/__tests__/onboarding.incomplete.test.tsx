import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import Page from '@/app/onboarding/page'
import * as api from '@/lib/api'

jest.mock('next/navigation', () => ({ useRouter: () => ({ replace: jest.fn() }) }))
jest.mock('@/lib/api')

describe('Onboarding page incomplete flow', () => {
  it('renders onboarding flow when status incomplete', async () => {
    ;(api.getOnboardingStatus as jest.Mock).mockResolvedValue({ completed: false, steps: [], current_step: 0 })
    ;(api.isAuthed as jest.Mock).mockReturnValue(true)
    render(<Page />)
    expect(screen.getByText(/Loading onboarding/i)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(/Step 1 of/i)).toBeInTheDocument())
  })
})


