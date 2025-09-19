import { apiFetch } from '@/lib/api/fetch';

describe('apiFetch auth guard', () => {
  let originalFetch: typeof global.fetch;
  let consoleErrorSpy: jest.SpyInstance;
  let consoleLogSpy: jest.SpyInstance;
  let consoleWarnSpy: jest.SpyInstance;

  beforeEach(() => {
    originalFetch = global.fetch;
    consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined);
    consoleLogSpy = jest.spyOn(console, 'log').mockImplementation(() => undefined);
    consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation(() => undefined);
  });

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    }
    consoleErrorSpy.mockRestore();
    consoleLogSpy.mockRestore();
    consoleWarnSpy.mockRestore();
    jest.clearAllMocks();
  });

  const createHeaders = (values: Record<string, string>) => {
    const normalized = Object.entries(values).reduce<Record<string, string>>((acc, [key, value]) => {
      acc[key.toLowerCase()] = value;
      return acc;
    }, {});

    return {
      entries: function* () {
        yield* Object.entries(normalized);
      },
      get: (key: string) => normalized[key.toLowerCase()] ?? null,
      has: (key: string) => normalized[key.toLowerCase()] !== undefined,
    } as Pick<Headers, 'entries' | 'get' | 'has'>;
  };

  const makeResponse = (overrides?: Partial<Response>, headerOverrides?: Record<string, string>): Response => {
    const headers = createHeaders({ 'content-type': 'application/json', 'content-length': '0', ...(headerOverrides || {}) });
    const base: Partial<Response> = {
      ok: true,
      status: 200,
      statusText: 'OK',
      url: 'http://localhost:8000/v1/auth/login',
      headers: headers as any,
      clone() {
        return makeResponse(overrides, headerOverrides);
      },
      json: async () => ({}),
      text: async () => '',
    };
    return Object.assign({}, base, overrides) as Response;
  };

  it('blocks auth calls without an orchestrator marker', async () => {
    const fetchMock = jest.fn();
    global.fetch = fetchMock as any;

    await expect(
      apiFetch('/v1/auth/login?username=test', { method: 'POST', body: JSON.stringify({}) })
    ).rejects.toThrow('Direct auth call not allowed');

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('allows auth calls with a legitimate orchestrator marker', async () => {
    const fetchMock = jest.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.includes('/v1/csrf')) {
        return Promise.resolve(
          makeResponse(
            {
              json: async () => ({ csrf_token: 'test-csrf' }),
              url,
            },
            { 'content-type': 'application/json' }
          )
        );
      }
      return Promise.resolve(makeResponse({ url }));
    });

    global.fetch = fetchMock as any;

    const response = await apiFetch('/v1/auth/login', {
      method: 'POST',
      headers: { 'X-Auth-Orchestrator': 'legitimate' },
      body: JSON.stringify({ username: 'demo', password: 'secret' }),
    });

    expect((response as any).ok).toBe(true);
    expect(fetchMock).toHaveBeenCalled();
  });

  it('allows debug bypass orchestrator markers', async () => {
    const fetchMock = jest.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.includes('/v1/csrf')) {
        return Promise.resolve(
          makeResponse(
            {
              json: async () => ({ csrf_token: 'test-csrf' }),
              url,
            },
            { 'content-type': 'application/json' }
          )
        );
      }
      return Promise.resolve(makeResponse({ url }));
    });

    global.fetch = fetchMock as any;

    const response = await apiFetch('/v1/auth/login', {
      method: 'POST',
      headers: { 'X-Auth-Orchestrator': 'debug-bypass' },
      body: JSON.stringify({ username: 'demo', password: 'secret' }),
    });

    expect((response as any).ok).toBe(true);
    expect(fetchMock).toHaveBeenCalled();
  });
});
