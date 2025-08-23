import React from 'react'
import { render } from '@testing-library/react'
import '@testing-library/jest-dom'
import { FooterRibbon } from '@/components/tv/surfaces/FooterRibbon'

describe('FooterRibbon', () => {
    it('does not render without text by default', () => {
        const { container } = render(<FooterRibbon />)
        expect(container.firstChild).toBeNull()
    })
})
