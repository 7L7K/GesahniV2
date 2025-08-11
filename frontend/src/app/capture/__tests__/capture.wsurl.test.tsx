import '@testing-library/jest-dom'
import { wsUrl } from '@/lib/api'

describe('wsUrl', () => {
  it('appends access token when present', () => {
    const store: Record<string, string> = { 'auth:access_token': 'abc' }
    Object.defineProperty(window, 'localStorage', { value: {
      getItem: (k: string) => store[k] || null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: (i: number) => Object.keys(store)[i] || null,
      length: 0,
    }, configurable: true })
    const url = wsUrl('/v1/transcribe')
    expect(url).toMatch(/access_token=/)
  })
})


