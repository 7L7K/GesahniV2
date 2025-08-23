import React from 'react'
import { act, render } from '@testing-library/react'
import '@testing-library/jest-dom'
import { VibeSwitcher } from '@/components/tv/layers/VibeSwitcher'

describe('VibeSwitcher', () => {
    it('toggles open on longpress', async () => {
        const { getByText, queryByText } = render(<VibeSwitcher />)
        expect(queryByText('Vibe')).not.toBeInTheDocument()
        await act(async () => { window.dispatchEvent(new CustomEvent('remote:longpress:ok')) })
        expect(getByText('Vibe')).toBeInTheDocument()
    })
})
