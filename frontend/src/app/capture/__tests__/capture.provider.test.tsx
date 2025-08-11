import React from 'react'
import { render } from '@testing-library/react'
import '@testing-library/jest-dom'
import { RecorderProvider } from '@/components/recorder/RecorderProvider'

describe('RecorderProvider', () => {
  it('mounts without crashing', () => {
    render(<RecorderProvider><div>child</div></RecorderProvider>)
  })
})


