import React from 'react'
import { act, render } from '@testing-library/react'
import '@testing-library/jest-dom'
import { AlertLayer } from '@/components/tv/layers/AlertLayer'

describe('AlertLayer', () => {
    it('renders on alert:incoming', async () => {
        const { container } = render(<AlertLayer />)
        await act(async () => {
            window.dispatchEvent(new CustomEvent('alert:incoming', { detail: { event: 'alert.help' } } as any))
        })
        expect(container.querySelector('div')).not.toBeNull()
    })
})


