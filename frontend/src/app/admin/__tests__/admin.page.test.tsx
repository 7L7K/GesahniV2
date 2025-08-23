/** @jest-environment jsdom */
import React from 'react'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'
import Page from '../../admin/page'

jest.mock('next/navigation', () => ({ useRouter: () => ({ replace: jest.fn() }) }))

describe('Admin /admin page', () => {
    beforeEach(() => {
        ; (process as any).env.NEXT_PUBLIC_ADMIN_TOKEN = 't'
            ; (global as any).fetch = jest.fn(async (url: any) => {
                if (String(url).includes('/v1/admin/router/decisions')) {
                    return new Response(JSON.stringify({ items: [] }), { status: 200, headers: { 'content-type': 'application/json' } } as any) as any
                }
                if (String(url).includes('/v1/admin/errors')) {
                    return new Response(JSON.stringify({ errors: [] }), { status: 200, headers: { 'content-type': 'application/json' } } as any) as any
                }
                if (String(url).includes('/v1/admin/self_review')) {
                    return new Response(JSON.stringify({ status: 'unavailable' }), { status: 200, headers: { 'content-type': 'application/json' } } as any) as any
                }
                return new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } } as any) as any
            })
    })

    afterEach(() => {
        ; (global as any).fetch = undefined
    })

    it('renders headings', async () => {
        const qc = new QueryClient()
        render(<QueryClientProvider client={qc}><Page /></QueryClientProvider>)
        expect(await screen.findByText(/Router Decisions/i)).toBeInTheDocument()
        expect(await screen.findByText(/Daily self-review/i)).toBeInTheDocument()
    })
})
