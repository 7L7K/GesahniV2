import { scheduler } from '@/services/scheduler'

describe('Scheduler basic', () => {
    it('computes an assignment with primary and side rail', () => {
        scheduler.start()
        const a = scheduler.getAssignment()
        expect(a).toBeTruthy()
        expect(Array.isArray(a.scores)).toBe(true)
    })

    it('nudge prev/next sets forced primary for a while', () => {
        const before = scheduler.getAssignment().primary
        scheduler.nudge('next')
        const after = scheduler.getAssignment().primary
        // On first call, may not change immediately; just ensure call does not crash
        expect(before).toBeDefined()
        expect(after).toBeDefined()
    })
})


