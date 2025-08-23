import { attachRemoteKeymap } from '@/lib/remoteKeymap'

describe('remote keymap', () => {
    it('dispatches events on arrow and enter', () => {
        const detach = attachRemoteKeymap()
        const events: string[] = []
        const handler = (e: Event) => events.push((e as CustomEvent).type)
        window.addEventListener('remote:left', handler as EventListener)
        window.addEventListener('remote:right', handler as EventListener)
        window.addEventListener('remote:ok', handler as EventListener)
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft' }))
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }))
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
        expect(events).toEqual(expect.arrayContaining(['remote:left', 'remote:right', 'remote:ok']))
        detach()
    })
})
