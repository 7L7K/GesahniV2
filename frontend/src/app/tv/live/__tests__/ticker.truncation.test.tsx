import React from 'react'
import { render } from '@testing-library/react'
import '@testing-library/jest-dom'
import { FooterRibbon } from '@/components/tv/surfaces/FooterRibbon'

describe('Ticker truncation', () => {
    it('does not render when no last exchange', () => {
        const { container } = render(<FooterRibbon />)
        expect(container.firstChild).toBeNull()
    })
})
