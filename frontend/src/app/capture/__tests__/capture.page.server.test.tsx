// Server component guard: we can't execute Next.js server behavior here, but ensure module loads
import '@testing-library/jest-dom'
import * as pageModule from '@/app/capture/page'

describe('Capture page server module', () => {
  it('exports metadata and default', () => {
    expect(pageModule).toHaveProperty('metadata')
    expect(pageModule).toHaveProperty('default')
  })
})


