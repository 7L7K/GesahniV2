import '@testing-library/jest-dom'
import { apiFetch } from '@/lib/api'

describe('apiFetch /v1/ask', () => {
  const originalFetch = global.fetch
  beforeEach(() => {
    // @ts-ignore
    global.fetch = jest.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const u = String(url)
      if (u.includes('/v1/csrf')) {
        return new Response(JSON.stringify({ csrf_token: 't123' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      // Echo back request for assertions
      const headers = (init?.headers || {}) as any
      const hasCSRF = !!(headers['X-CSRF-Token'] || headers['x-csrf-token'])
      const hasAuth = !!(headers['Authorization'] || headers['authorization'])
      const body = JSON.stringify({
        url: u,
        method: init?.method || 'GET',
        credentials: init?.credentials || 'omit',
        hasCSRF,
        hasAuth,
      })
      return new Response(body, { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
  })
  afterAll(() => { global.fetch = originalFetch })

  it('includes credentials and X-CSRF-Token for POST /v1/ask', async () => {
    const r = await apiFetch('/v1/ask', { method: 'POST', body: JSON.stringify({ prompt: 'hi' }) })
    expect(r.status).toBe(200)
    const j = await r.json()
    expect(j.credentials).toBe('include')
    expect(j.hasCSRF).toBe(true)
  })
})

