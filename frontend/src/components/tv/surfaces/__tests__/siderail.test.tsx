import React from 'react'
import { render } from '@testing-library/react'
import '@testing-library/jest-dom'
import { SideRail } from '@/components/tv/surfaces/SideRail'

describe('SideRail', () => {
    beforeEach(() => {
        jest.spyOn(global as any, 'fetch').mockImplementation(async (url: string) => {
            if (url.includes('/tv/weather')) {
                return new (global as any).Response(JSON.stringify({ now: { temp: 70 } }), { status: 200, headers: { 'content-type': 'application/json' } })
            }
            if (url.includes('/tv/calendar/next')) {
                return new (global as any).Response(JSON.stringify({ items: [{ time: '09:00', title: 'Visit' }] }), { status: 200, headers: { 'content-type': 'application/json' } })
            }
            return new (global as any).Response('{}', { status: 200, headers: { 'content-type': 'application/json' } })
        })
    })
    afterEach(() => jest.restoreAllMocks())
    it('renders vitals and chips', () => {
        const { getAllByText } = render(<SideRail />)
        expect(getAllByText(/Temp|Next|Online|Offline|Reconnecting/).length).toBeGreaterThan(0)
    })
})
