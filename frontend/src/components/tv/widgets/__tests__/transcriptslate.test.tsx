import React from 'react'
import { act, render } from '@testing-library/react'
import '@testing-library/jest-dom'
import { TranscriptSlate } from '@/components/tv/widgets/TranscriptSlate'

describe('TranscriptSlate', () => {
    it('reacts to websocket messages', async () => {
        const { getByText } = render(<TranscriptSlate />)
        // simulate WS message
        await act(async () => {
            const ws: any = (global as any).WebSocket.mockInstance
            if (ws && ws.onmessage) ws.onmessage({ data: JSON.stringify({ text: 'hello', final: true }) })
        })
        expect(getByText('hello')).toBeInTheDocument()
    })
})
