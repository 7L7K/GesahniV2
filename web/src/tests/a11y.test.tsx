import React from 'react'
import { render } from '@testing-library/react'
import '@testing-library/jest-dom'
import { axe, toHaveNoViolations } from 'jest-axe'
import Home from '../app/page'

expect.extend(toHaveNoViolations)

describe('a11y', () => {
    it('has no critical violations on Home', async () => {
        const { container } = render(<Home />)
        const results = await axe(container, { rules: { 'color-contrast': { enabled: true } } })
        expect(results.violations.filter(v => v.impact === 'critical')).toHaveLength(0)
    })
})


