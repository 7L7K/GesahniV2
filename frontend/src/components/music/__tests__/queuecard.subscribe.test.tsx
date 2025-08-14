import React from 'react'
import { render, screen, act } from '@testing-library/react'
import QueueCard from '../QueueCard'

jest.mock('@/lib/api', () => ({
    getQueue: jest.fn(async () => ({ up_next: [{ id: 't1', name: 'S1', artists: 'A', art_url: '' }], skip_count: 0 })),
}))

describe('QueueCard subscribes to hub events', () => {
    it('refreshes when music.queue.updated is dispatched (no direct WebSocket)', async () => {
        render(<QueueCard />)
        expect(await screen.findByText('S1')).toBeInTheDocument()
            ; (jest.requireMock('@/lib/api') as any).getQueue.mockResolvedValueOnce({ up_next: [{ id: 't2', name: 'S2', artists: 'B', art_url: '' }], skip_count: 1 })
        await act(async () => { window.dispatchEvent(new CustomEvent('music.queue.updated', { detail: {} } as any)) })
        expect(await screen.findByText('S2')).toBeInTheDocument()
        // Ensure no component-level WebSocket was created
        expect(((global as any).WebSocket?.mock?.calls || []).some((c: any[]) => String(c?.[0] || '').includes('/v1/ws/music'))).toBe(false)
    })
})


