import { attachUiEffects } from '@/lib/uiEffects'

describe('uiEffects', () => {
    beforeEach(() => {
        jest.spyOn(global as any, 'fetch').mockResolvedValue(new (global as any).Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }))
    })
    afterEach(() => jest.restoreAllMocks())
    it('reacts to ui intents', async () => {
        const detach = attachUiEffects()
        window.dispatchEvent(new CustomEvent('ui.duck'))
        window.dispatchEvent(new CustomEvent('ui.restore'))
        window.dispatchEvent(new CustomEvent('ui.vibe.changed', { detail: { vibe: 'Calm Night' } } as any))
        detach()
    })
})
