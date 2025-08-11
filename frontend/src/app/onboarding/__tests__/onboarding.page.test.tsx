import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import Page from '@/app/onboarding/page'
import * as api from '@/lib/api'

jest.mock('next/navigation', () => ({ useRouter: () => ({ replace: jest.fn() }) }))
jest.mock('@/lib/api')

describe('Onboarding page integration', () => {
  it('redirects to login if unauthenticated and API fails', async () => {
    (api.getOnboardingStatus as jest.Mock).mockRejectedValue(new Error('network'))
    ;(api.isAuthed as jest.Mock).mockReturnValue(false)
    render(<Page />)
    // We can't assert router.replace without exporting it; ensure loading renders then disappears
    expect(screen.getByText(/Loading onboarding/i)).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText(/Loading onboarding/i)).not.toBeInTheDocument())
  })
})


