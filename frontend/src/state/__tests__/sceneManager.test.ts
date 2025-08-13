import { act } from '@testing-library/react'
import { useSceneManager } from '@/state/sceneManager'

jest.useFakeTimers()

describe('SceneManager', () => {
    it('auto-returns to ambient after 8s in interactive', () => {
        const store = useSceneManager.getState()
        store.toInteractive('user_interaction')
        expect(useSceneManager.getState().scene).toBe('interactive')
        act(() => { jest.advanceTimersByTime(8000) })
        expect(useSceneManager.getState().scene).toBe('ambient')
    })

    it('guarded: interactive has no effect when in alert', () => {
        const store = useSceneManager.getState()
        store.toAlert('ws_alert')
        store.toInteractive('user_interaction')
        expect(useSceneManager.getState().scene).toBe('alert')
    })
})


