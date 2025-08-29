'use client';

import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { listDevices } from '@/lib/api';

export function useSpotifyStatus(pollMs: number = 30000) {
  const [connected, setConnected] = useState<boolean>(false);
  const [reason, setReason] = useState<string | null>(null);
  const [hasChecked, setHasChecked] = useState<boolean>(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    let mounted = true;
    const poll = async () => {
      try {
        const res = await apiFetch('/v1/spotify/status', { auth: true, dedupe: false, cache: 'no-store' });
        setHasChecked(true);
        if (!mounted) return;
        if (res.ok) {
          const body = await res.json().catch(() => ({} as any));
          setConnected(Boolean(body?.connected));
          setReason(body?.reason || null);
        } else {
          setConnected(false);
          setReason(res.status === 401 ? 'auth_required' : `http_${res.status}`);
        }
      } catch {
        if (!mounted) return;
        setHasChecked(true);
        setConnected(false);
        setReason('network_error');
      } finally {
        if (!mounted) return;
        timerRef.current = window.setTimeout(poll, pollMs);
      }
    };
    poll();
    return () => { mounted = false; if (timerRef.current) window.clearTimeout(timerRef.current); };
  }, [pollMs]);

  return { connected, reason, hasChecked } as const;
}

export function useMusicDevices(pollMs: number = 45000) {
  const [devices, setDevices] = useState<any[]>([]);
  const [hasChecked, setHasChecked] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    let mounted = true;
    const poll = async () => {
      try {
        const resp = await listDevices();
        setHasChecked(true);
        if (!mounted) return;
        setDevices(Array.isArray(resp?.devices) ? resp.devices : []);
      } catch {
        if (!mounted) return;
        setHasChecked(true);
      } finally {
        if (!mounted) return;
        timerRef.current = window.setTimeout(poll, pollMs);
      }
    };
    poll();
    return () => { mounted = false; if (timerRef.current) window.clearTimeout(timerRef.current); };
  }, [pollMs]);

  const hasDevice = devices && devices.length > 0;
  return { devices, hasDevice, hasChecked } as const;
}

