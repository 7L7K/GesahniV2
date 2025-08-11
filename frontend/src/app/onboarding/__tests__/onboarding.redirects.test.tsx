import React from 'react'
import { render, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import Page from '@/app/onboarding/page'
import * as api from '@/lib/api'

const replace = jest.fn()
jest.mock('next/navigation', () => ({ useRouter: () => ({ replace }) }))
jest.mock('@/lib/api')

describe('Onboarding redirects', () => {
  beforeEach(() => { replace.mockReset() })

  it('redirects to / when onboarding completed', async () => {
    ;(api.getOnboardingStatus as jest.Mock).mockResolvedValue({ completed: true, steps: [], current_step: 0 })
    render(<Page />)
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/'))
  })
})


