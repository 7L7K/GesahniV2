import React from 'react'
import { render, screen, act } from '@testing-library/react'
import DiscoveryCard from '../DiscoveryCard'

jest.mock('@/lib/api', () => ({
    getRecommendations: jest.fn(async () => ({ recommendations: [{ id: 't1', name: 'R1', artists: 'A', art_url: '' }] })),
}))

describe('DiscoveryCard subscribes to hub events', () => {
    it('refreshes when music.state is dispatched (no direct WebSocket)', async () => {
        render(<DiscoveryCard />)
        expect(await screen.findByText('R1')).toBeInTheDocument()
            ; (jest.requireMock('@/lib/api') as any).getRecommendations.mockResolvedValueOnce({ recommendations: [{ id: 't2', name: 'R2', artists: 'B', art_url: '' }] })
        await act(async () => { window.dispatchEvent(new CustomEvent('music.state', { detail: { vibe: { energy: 0.2 } } } as any)) })
        expect(await screen.findByText('R2')).toBeInTheDocument()
        expect(((global as any).WebSocket?.mock?.calls || []).some((c: any[]) => String(c?.[0] || '').includes('/v1/ws/music'))).toBe(false)
    })
})


