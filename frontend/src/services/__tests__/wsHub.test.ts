import { wsHub } from '@/services/wsHub'

describe('wsHub', () => {
    it('starts and stops without error', () => {
        wsHub.start()
        wsHub.stop()
    })

    it('dispatches tv.config.updated event (care channel)', () => {
        // Ensure hub is connected to care only
        wsHub.start({ care: true, music: false })
        // Find the care WebSocket mock instance
        const calls = (global as any).WebSocket?.mock?.calls || []
        const careCallIdx = calls.findIndex((c: any[]) => String(c?.[0] || '').includes('/v1/ws/care'))
        expect(careCallIdx).toBeGreaterThanOrEqual(0)
        const careWs = (global as any).WebSocket.mock.instances[careCallIdx]
        const events: Event[] = []
        const spy = jest.spyOn(window, 'dispatchEvent').mockImplementation((ev: Event) => { events.push(ev); return true })
        const payload = { topic: 'resident:me', data: { event: 'tv.config.updated', config: { rail: 'safe' } } }
        careWs.onmessage && careWs.onmessage({ data: JSON.stringify(payload) })
        expect(events.some((e) => (e as CustomEvent).type === 'tv.config.updated')).toBe(true)
        spy.mockRestore()
        wsHub.stop({ care: true, music: false })
    })

    it('queues outbound messages and flushes after reconnect', () => {
        wsHub.start({ care: true, music: false })
        const calls = (global as any).WebSocket?.mock?.calls || []
        const careCallIdx = calls.findIndex((c: any[]) => String(c?.[0] || '').includes('/v1/ws/care'))
        const careWs = (global as any).WebSocket.mock.instances[careCallIdx]
        // Force closed state
        careWs.readyState = 3 // CLOSED
            // Queue a message while offline
            ; (wsHub as any).sendCare({ ping: true })
        // Simulate reconnect
        const nextIdx = (global as any).WebSocket.mock.instances.length
        // trigger onclose to schedule reconnect
        careWs.onclose && careWs.onclose({})
        // Create another WS instance and mark it OPEN
        const newCareCallIdx = (global as any).WebSocket.mock.calls.findIndex((c: any[]) => String(c?.[0] || '').includes('/v1/ws/care') && (global as any).WebSocket.mock.calls.indexOf(c) > careCallIdx)
        const newCareWs = (global as any).WebSocket.mock.instances[newCareCallIdx]
        newCareWs.readyState = (global as any).WebSocket.OPEN // OPEN
        newCareWs.send = jest.fn()
        // Fire onopen to flush queue
        newCareWs.onopen && newCareWs.onopen({})
        expect(newCareWs.send).toHaveBeenCalled()
        wsHub.stop({ care: true, music: false })
    })

    it('is idempotent under StrictMode (multiple start calls only connect once)', () => {
        const WS = (global as any).WebSocket
        WS.mockClear()
        wsHub.start({ music: true })
        wsHub.start({ music: true })
        wsHub.start({ music: true })
        // Expect only one connection per socket path for music
        const paths = WS.mock.calls.map((c: any[]) => String(c?.[0] || ''))
        const musicCount = paths.filter((p: string) => p.includes('/v1/ws/music')).length
        expect(musicCount).toBe(1)
        // stop thrice should fully close
        wsHub.stop({ music: true })
        wsHub.stop({ music: true })
        wsHub.stop({ music: true })
    })
})


