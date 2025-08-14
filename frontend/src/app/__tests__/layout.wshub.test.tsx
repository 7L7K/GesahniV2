import React from 'react'
import { render } from '@testing-library/react'
import RootLayout from '../layout'

describe('RootLayout WsBootstrap', () => {
    it('does not create duplicate music WebSocket connections when mounted twice (StrictMode-like)', () => {
        const WS = (global as any).WebSocket
        WS.mockClear()
        const wrapper = ({ children }: any) => (
            <html><body>{children}</body></html>
        )
        // Render RootLayout twice to simulate StrictMode double-invoke
        render(<RootLayout><div>child</div></RootLayout>, { wrapper })
        render(<RootLayout><div>child</div></RootLayout>, { wrapper })
        const calls = WS.mock.calls.map((c: any[]) => String(c?.[0] || ''))
        const musicCount = calls.filter((p: string) => p.includes('/v1/ws/music')).length
        expect(musicCount).toBeLessThanOrEqual(1)
        // care channel should not be started at layout level
        expect(calls.some((p: string) => p.includes('/v1/ws/care'))).toBe(false)
    })
})


