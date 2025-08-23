import React from 'react';
import { render } from '@testing-library/react';
import Page from '../page';

jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn(), replace: jest.fn() }) }));

describe('TV Page smoke', () => {
    test('renders without crash', () => {
        render(<Page />);
    });
});

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
        // multiple "You said:" elements exist; ensure at least one is present
        expect(screen.getAllByText(/You said:/).length).toBeGreaterThanOrEqual(1)
    })

    it('Yes/No bar always shows buttons', () => {
        render(<YesNoBar />)
        expect(screen.getByText('Yes')).toBeInTheDocument()
        expect(screen.getByText('No')).toBeInTheDocument()
    })

    it('Caption bar displays spoken text', () => {
        render(<CaptionBar text="hello" />)
        expect(screen.getAllByText(/You said:/).length).toBeGreaterThanOrEqual(1)
        expect(screen.getByText('hello')).toBeInTheDocument()
    })
})
