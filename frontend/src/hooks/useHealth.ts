'use client';

import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { useAuthState } from '@/hooks/useAuth';

export type HealthChecks = Record<string, 'ok' | 'error' | 'degraded' | 'skipped' | string>;
export type HealthSnapshot = { status: 'ok' | 'degraded' | 'fail' | string; checks?: HealthChecks } | null;

export function useHealthPolling(intervalMs: number = 15000) {
  const auth = useAuthState();
  const [health, setHealth] = useState<HealthSnapshot>(null);
  const [hasChecked, setHasChecked] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    let mounted = true;
    const poll = async () => {
      if (!(auth.is_authenticated && auth.whoamiOk)) return;
      try {
        const res = await apiFetch('/v1/health', { auth: true, dedupe: false, cache: 'no-store' });
        setHasChecked(true);
        if (!mounted) return;
        if (res.ok) {
          const body = await res.json().catch(() => null);
          if (mounted) setHealth(body);
        } else {
          if (mounted) setHealth({ status: 'fail' });
        }
      } catch {
        if (mounted) setHealth({ status: 'fail' });
        setHasChecked(true);
      } finally {
        if (!mounted) return;
        timerRef.current = window.setTimeout(poll, intervalMs);
      }
    };
    poll();
    return () => { mounted = false; if (timerRef.current) window.clearTimeout(timerRef.current); };
  }, [auth.is_authenticated, auth.whoamiOk, intervalMs]);

  const llamaStatus = (health?.checks?.["llama"] || '').toString();
  const llamaDegraded = llamaStatus === 'error' || llamaStatus === 'degraded';

  return { health, hasChecked, llamaDegraded };
}

