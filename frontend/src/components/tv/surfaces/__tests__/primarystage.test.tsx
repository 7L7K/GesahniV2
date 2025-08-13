import React from 'react'
import { render } from '@testing-library/react'
import '@testing-library/jest-dom'
import { PrimaryStage } from '@/components/tv/surfaces/PrimaryStage'

describe('PrimaryStage', () => {
    it('renders without crashing', () => {
        render(<PrimaryStage />)
    })
})


