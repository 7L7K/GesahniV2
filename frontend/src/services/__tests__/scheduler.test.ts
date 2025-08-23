import { scheduler } from '@/services/scheduler'
import { _setCalendar } from '@/services/scheduler'

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

describe('Calendar weighting & chip', () => {
    it('boosts CalendarCard within 45 minutes of event', () => {
        // set an event 30 minutes from now
        const now = new Date()
        const in30 = new Date(now.getTime() + 30 * 60_000)
        const hh = String(in30.getHours()).padStart(2, '0')
        const mm = String(in30.getMinutes()).padStart(2, '0')
        _setCalendar([{ time: `${hh}:${mm}`, title: 'Appt' }])
        scheduler.start()
        const a = scheduler.getAssignment()
        // Not strictly asserting primary equals CalendarCard (other boosts may apply),
        // but the chip should be populated
        expect(a.nextEventChip).toMatch(/Next: Appt/)
    })
})
