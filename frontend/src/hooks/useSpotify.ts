'use client';

import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { getAuthOrchestrator } from '@/services/authOrchestrator';
import { listDevices } from '@/lib/api';

export function useSpotifyStatus(pollMs: number = 30000) {
  const [connected, setConnected] = useState<boolean>(false);
  const [reason, setReason] = useState<string | null>(null);
  const [hasChecked, setHasChecked] = useState<boolean>(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    let mounted = true;
    const poll = async () => {
      // Gate on auth orchestrator readiness
      try {
        const s: any = getAuthOrchestrator().getState();
        const isAuthed = Boolean(s.is_authenticated ?? s.isAuthenticated);
        const ready = Boolean(s.session_ready ?? s.sessionReady);
        if (!(isAuthed && ready)) {
          setHasChecked(true);
          setConnected(false);
          setReason('auth_required');
          timerRef.current = window.setTimeout(poll, pollMs);
          return;
        }
      } catch { /* ignore and proceed */ }
      try {
        // Probe live endpoints directly instead of /v1/spotify/status
        const [devResSettled, stateResSettled] = await Promise.allSettled([
          apiFetch('/v1/spotify/devices', { auth: true, dedupe: false, cache: 'no-store' }),
          apiFetch('/v1/state', { auth: true, dedupe: false, cache: 'no-store' }),
        ]);

        setHasChecked(true);
        if (!mounted) return;

        let devices_ok = false;
        let state_ok = false;
        let unauth = false;
        let rateLimited = false;

        if (devResSettled.status === 'fulfilled') {
          const r = devResSettled.value;
          devices_ok = r.ok;
          unauth = unauth || r.status === 401;
          rateLimited = rateLimited || r.status === 429;
        }
        if (stateResSettled.status === 'fulfilled') {
          const r = stateResSettled.value;
          state_ok = r.ok;
          unauth = unauth || r.status === 401;
          rateLimited = rateLimited || r.status === 429;
        }

        const isConnected = devices_ok || state_ok;
        setConnected(isConnected);
        if (isConnected) {
          setReason(null);
        } else if (unauth) {
          setReason('auth_required');
        } else if (rateLimited) {
          setReason('rate_limited');
        } else {
          setReason('disconnected');
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
