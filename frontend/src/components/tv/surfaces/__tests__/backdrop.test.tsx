import React from 'react'
import { render } from '@testing-library/react'
import { Backdrop } from '@/components/tv/surfaces/Backdrop'

describe('Backdrop', () => {
    it('renders children under dim layer', () => {
        const { getByText } = render(<div style={{ position: 'relative', width: 300, height: 200 }}><Backdrop><div>child</div></Backdrop></div>)
        expect(getByText('child')).toBeInTheDocument()
    })
})
