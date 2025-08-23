import React from 'react'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import { WeatherPeek } from '@/components/tv/widgets/WeatherPeek'

describe('WeatherPeek', () => {
    beforeEach(() => {
        jest.spyOn(global as any, 'fetch').mockResolvedValue(new (global as any).Response(JSON.stringify({ now: { temp: 70, desc: 'Sunny', sentence: '70F and Sunny' }, today: { high: 72, low: 60 }, tomorrow: { high: 71, low: 59 } }), { status: 200, headers: { 'content-type': 'application/json' } }))
    })
    afterEach(() => jest.restoreAllMocks())
    it('renders tiles', async () => {
        render(<WeatherPeek />)
        expect(await screen.findByText('Now')).toBeInTheDocument()
    })
})
