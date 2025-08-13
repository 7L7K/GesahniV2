import React from 'react'
import { render } from '@testing-library/react'
import '@testing-library/jest-dom'
import { axe, toHaveNoViolations } from 'jest-axe'
import Home from '../app/page'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
jest.mock('../lib/apiFetch', () => ({
    apiFetch: async (_url: string) => {
        if (_url.includes('/v1/profile')) return { name: 'Test User' }
        if (_url.includes('/v1/admin/metrics')) return { metrics: { total: 1, llama: 0, gpt: 1, fallback: 0, cache_hits: 1, cache_lookups: 1, ha_failures: 0 }, cache_hit_rate: 100 }
        return {}
    }
}))

expect.extend(toHaveNoViolations)

describe('a11y', () => {
    it('has no critical violations on Home', async () => {
        const qc = new QueryClient()
        const { container } = render(
            <QueryClientProvider client={qc}>
                <Home />
            </QueryClientProvider>
        )
        const results = await axe(container, { rules: { 'color-contrast': { enabled: true } } })
        expect(results.violations.filter(v => v.impact === 'critical')).toHaveLength(0)
    })
})


