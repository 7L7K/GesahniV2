'use client';

import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api/fetch';
import { useAuthState } from '@/hooks/useAuth';

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
  authState?: any;
};

export default function EnvCanaryPage() {
  const [data, setData] = useState<Canary | null>(null);
  const authState = useAuthState();

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
        authState: {
          is_authenticated: authState.is_authenticated,
          session_ready: authState.session_ready,
          user_id: authState.user_id,
          source: authState.source,
          whoamiOk: authState.whoamiOk,
          error: authState.error,
          lastChecked: authState.lastChecked,
        },
      };

      // Note: Removed direct whoami call to avoid violating AuthOrchestrator contract
      // Auth state is now provided by useAuthState hook above

      setData(snapshot);
    };
    run();
  }, [authState]);

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-3">Env Canary</h1>
      <p className="text-sm text-gray-600 mb-4">Quick check for origin/proxy and auth state. (Note: Shows AuthOrchestrator state, not direct API calls)</p>
      <pre className="text-xs bg-gray-100 rounded p-4 overflow-auto">{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}
