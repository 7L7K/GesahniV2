import { wsHub } from '@/services/wsHub'

describe('wsHub', () => {
    it('starts and stops without error', () => {
        wsHub.start()
        wsHub.stop()
    })
})


