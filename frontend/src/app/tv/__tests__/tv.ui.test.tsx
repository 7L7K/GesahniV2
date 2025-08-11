import React from 'react'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import TvHome from '../../tv/page'
import Listening from '../../tv/listening/page'
import { YesNoBar } from '@/components/tv/YesNoBar'
import { CaptionBar } from '@/components/tv/CaptionBar'

describe('TV UI basics', () => {
    it('Home screen renders large tiles', () => {
        render(<TvHome />)
        expect(screen.getByText('Granny Mode')).toBeInTheDocument()
            ;['Weather', 'Calendar', 'Music', 'Photos'].forEach(label => {
                expect(screen.getByText(label)).toBeInTheDocument()
            })
    })

    it('Listening screen shows live caption structure', () => {
        render(<Listening />)
        expect(screen.getByText('Listening…')).toBeInTheDocument()
        expect(screen.getByText(/You said:/)).toBeInTheDocument()
    })

    it('Yes/No bar always shows buttons', () => {
        render(<YesNoBar />)
        expect(screen.getByText('Yes')).toBeInTheDocument()
        expect(screen.getByText('No')).toBeInTheDocument()
    })

    it('Caption bar displays spoken text', () => {
        render(<CaptionBar text="hello" />)
        expect(screen.getByText(/You said:/)).toBeInTheDocument()
        expect(screen.getByText('hello')).toBeInTheDocument()
    })
})


