import React from 'react'
import { render, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import { AlertPanel } from '@/components/tv/widgets/AlertPanel'

describe('AlertPanel', () => {
    beforeEach(() => {
        jest.spyOn(global as any, 'fetch').mockResolvedValue(new (global as any).Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }))
    })
    afterEach(() => jest.restoreAllMocks())
    it('renders and can cancel', () => {
        const { getByText } = render(<AlertPanel />)
        fireEvent.click(getByText('Cancel'))
    })
})


