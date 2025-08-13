import { wsHub } from '@/services/wsHub'

describe('wsHub', () => {
    it('starts and stops without error', () => {
        wsHub.start()
        wsHub.stop()
    })

    it('dispatches tv.config.updated event', () => {
        // Ensure hub is connected
        wsHub.start()
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
        wsHub.stop()
    })

    it('queues outbound messages and flushes after reconnect', () => {
        wsHub.start()
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
        wsHub.stop()
    })
})


