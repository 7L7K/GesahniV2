import React from 'react'
import { render, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { PhotoFrame } from '@/components/tv/widgets/PhotoFrame'

describe('PhotoFrame', () => {
    beforeEach(() => {
        jest.spyOn(global as any, 'fetch').mockResolvedValue(new (global as any).Response(JSON.stringify({ folder: '/shared_photos', items: ['a.jpg', 'b.jpg'] }), { status: 200, headers: { 'content-type': 'application/json' } }))
    })
    afterEach(() => {
        jest.restoreAllMocks()
    })
    it('renders placeholder and then an image', async () => {
        const { getByText, findAllByRole } = render(<PhotoFrame />)
        expect(getByText('No photos found')).toBeInTheDocument()
        const imgs = await findAllByRole('img')
        expect(imgs.length).toBeGreaterThan(0)
    })
})


