import React from 'react'
import { render } from '@testing-library/react'
import '@testing-library/jest-dom'
import Page from '../page'

describe('TV Live page', () => {
    it('renders without crashing', () => {
        render(<Page />)
    })
})
