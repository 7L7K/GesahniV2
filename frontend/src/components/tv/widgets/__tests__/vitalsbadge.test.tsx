import React from 'react'
import { render } from '@testing-library/react'
import '@testing-library/jest-dom'
import { VitalsBadge } from '@/components/tv/widgets/VitalsBadge'

describe('VitalsBadge', () => {
    it('shows Online or Offline', () => {
        const { getByText } = render(<VitalsBadge />)
        // Either Online ✓ or Offline/Reconnecting… may appear depending on env
        expect(getByText(/Online|Offline|Reconnecting/)).toBeInTheDocument()
    })
})


