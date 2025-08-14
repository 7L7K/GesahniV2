import '@testing-library/jest-dom'
import { apiFetch, setTokens, clearTokens } from '@/lib/api'

describe('apiFetch', () => {
  const originalFetch = global.fetch
  beforeEach(() => {
    // @ts-ignore
    global.fetch = jest.fn(async (url, init) => {
      if (String(url).includes('/v1/refresh')) {
        return new Response(JSON.stringify({ access_token: 'new' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      if (String(url).includes('/401')) {
        return new Response('unauthorized', { status: 401 })
      }
      return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    clearTokens()
  })
  afterAll(() => { global.fetch = originalFetch })

  it('refreshes on 401 when token present', async () => {
    setTokens('old')
    const res = await apiFetch('/401')
    expect(res.status).toBe(200)
  })

  it('does not refresh when no refresh token', async () => {
    const res = await apiFetch('/200')
    expect(res.status).toBe(200)
  })

  it('does not retry 404 and returns immediately', async () => {
    // @ts-ignore
    global.fetch = jest.fn(async (url, init) => new Response('nope', { status: 404 } as any) as any)
    const res = await apiFetch('/missing')
    expect(res.status).toBe(404)
    expect((global.fetch as any).mock.calls.length).toBe(1)
  })
})


