'use client';

import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api/fetch';

type Canary = {
  runtime: {
    windowOrigin: string | null;
    locationHref: string | null;
    documentCookie: string | null;
  };
  env: Record<string, string | undefined>;
  derived: {
    mode: 'proxy' | 'direct';
    apiBase: string;
  };
  whoami?: {
    ok: boolean;
    status: number;
    headers: Record<string, string>;
    body: any;
  } | { error: string };
};

export default function EnvCanaryPage() {
  const [data, setData] = useState<Canary | null>(null);

  useEffect(() => {
    const run = async () => {
      const useProxy = (process.env.NEXT_PUBLIC_USE_DEV_PROXY || 'false') === 'true';
      const apiOrigin = (process.env.NEXT_PUBLIC_API_ORIGIN || '').replace(/\/$/, '');
      const apiBase = useProxy ? '' : apiOrigin;

      const snapshot: Canary = {
        runtime: {
          windowOrigin: typeof window !== 'undefined' ? window.location.origin : null,
          locationHref: typeof window !== 'undefined' ? window.location.href : null,
          documentCookie: typeof document !== 'undefined' ? document.cookie : null,
        },
        env: {
          NEXT_PUBLIC_USE_DEV_PROXY: process.env.NEXT_PUBLIC_USE_DEV_PROXY,
          NEXT_PUBLIC_API_ORIGIN: process.env.NEXT_PUBLIC_API_ORIGIN,
          NODE_ENV: process.env.NODE_ENV,
        },
        derived: {
          mode: useProxy ? 'proxy' : 'direct',
          apiBase,
        },
      };

      try {
        const res = await apiFetch('/v1/whoami', { credentials: 'include' });
        const headers = Object.fromEntries(res.headers.entries());
        let body: any = null;
        try { body = await res.clone().json(); } catch { body = await res.text().catch(() => null); }
        snapshot.whoami = { ok: res.ok, status: res.status, headers, body };
      } catch (e: any) {
        snapshot.whoami = { error: e?.message || String(e) };
      }

      setData(snapshot);
    };
    run();
  }, []);

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-3">Env Canary</h1>
      <p className="text-sm text-gray-600 mb-4">Quick check for origin/proxy and whoami.</p>
      <pre className="text-xs bg-gray-100 rounded p-4 overflow-auto">{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}

