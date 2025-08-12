/** @jest-environment jsdom */
import React from 'react'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'
import Page from '../../metrics/page'

describe('Admin /admin/metrics page', () => {
    beforeEach(() => {
        ; (process as any).env.NEXT_PUBLIC_ADMIN_TOKEN = 't'
            ; (global as any).fetch = jest.fn(async (url: any) => {
                if (String(url).includes('/v1/admin/metrics')) {
                    return new Response(JSON.stringify({ metrics: { total: 1 }, cache_hit_rate: 0, top_skills: [] }), { status: 200, headers: { 'content-type': 'application/json' } } as any) as any
                }
                return new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } } as any) as any
            })
    })
    afterEach(() => { (global as any).fetch = undefined })

    it('renders metrics values', async () => {
        const qc = new QueryClient()
        render(<QueryClientProvider client={qc}><Page /></QueryClientProvider>)
        expect(await screen.findByText(/Admin Metrics/i)).toBeInTheDocument()
        expect(await screen.findByText(/Cache Hit Rate/i)).toBeInTheDocument()
    })
})


