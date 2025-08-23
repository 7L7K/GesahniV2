import '@testing-library/jest-dom'
import { setTokens, getToken, clearTokens, isAuthed } from '@/lib/api'

describe('api auth tokens', () => {
  beforeEach(() => {
    const store: Record<string, string> = {}
    Object.defineProperty(window, 'localStorage', { value: {
      getItem: (k: string) => store[k] || null,
      setItem: (k: string, v: string) => { store[k] = v },
      removeItem: (k: string) => { delete store[k] },
      clear: () => { for (const k of Object.keys(store)) delete store[k] },
      key: (i: number) => Object.keys(store)[i] || null,
      length: 0,
    }, configurable: true })
  })

  it('sets and gets token', () => {
    setTokens('t')
    expect(getToken()).toBe('t')
    expect(isAuthed()).toBe(true)
  })

  it('clears tokens', () => {
    setTokens('t')
    clearTokens()
    expect(getToken()).toBeNull()
    expect(isAuthed()).toBe(false)
  })
})
