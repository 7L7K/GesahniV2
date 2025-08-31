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
    let pollCount = 0;

    const poll = async () => {
      pollCount++;
      console.log(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} starting`, {
        pollMs,
        timestamp: new Date().toISOString()
      });

      // Gate on auth orchestrator readiness: don't probe Spotify until session is ready
      try {
        const s: any = getAuthOrchestrator().getState();
        const isAuthed = Boolean(s.is_authenticated ?? s.isAuthenticated);
        const ready = Boolean(s.session_ready ?? s.sessionReady);
        if (!(isAuthed && ready)) {
          console.warn(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - Auth gate blocked, will retry in ${pollMs}ms`);
          setHasChecked(true);
          setConnected(false);
          setReason('auth_required');
          timerRef.current = window.setTimeout(poll, pollMs);
          return;
        }
      } catch (authError) {
        // If orchestrator lookup fails, avoid aggressive probing
        console.warn(`🎵 SPOTIFY STATUS HOOK: Auth orchestrator unavailable, deferring probe`, authError);
        setHasChecked(true);
        setConnected(false);
        setReason('auth_required');
        timerRef.current = window.setTimeout(poll, pollMs);
        return;
      }

      try {
        console.log(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - Probing endpoints...`);

        // Probe live endpoints directly instead of /v1/spotify/status
        const [devResSettled, stateResSettled] = await Promise.allSettled([
          apiFetch('/v1/spotify/devices', { auth: true, dedupe: false, cache: 'no-store' }),
          apiFetch('/v1/state', { auth: true, dedupe: false, cache: 'no-store' }),
        ]);

        console.log(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - Endpoint results`, {
          devicesSettled: devResSettled.status,
          stateSettled: stateResSettled.status,
          timestamp: new Date().toISOString()
        });

        setHasChecked(true);
        if (!mounted) {
          console.log(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - Component unmounted, skipping update`);
          return;
        }

        let devices_ok = false;
        let state_ok = false;
        let unauth = false;
        let rateLimited = false;

        if (devResSettled.status === 'fulfilled') {
          const r = devResSettled.value;
          devices_ok = r.ok;
          unauth = unauth || r.status === 401;
          rateLimited = rateLimited || r.status === 429;
          console.log(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - Devices endpoint`, {
            ok: r.ok,
            status: r.status,
            statusText: r.statusText,
            devicesOk: devices_ok,
            unauth: unauth,
            rateLimited: rateLimited
          });
        } else {
          console.error(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - Devices endpoint failed`, devResSettled.reason);
        }

        if (stateResSettled.status === 'fulfilled') {
          const r = stateResSettled.value;
          state_ok = r.ok;
          unauth = unauth || r.status === 401;
          rateLimited = rateLimited || r.status === 429;
          console.log(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - State endpoint`, {
            ok: r.ok,
            status: r.status,
            statusText: r.statusText,
            stateOk: state_ok,
            unauth: unauth,
            rateLimited: rateLimited
          });
        } else {
          console.error(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - State endpoint failed`, stateResSettled.reason);
        }

        const isConnected = devices_ok || state_ok;
        const finalReason = isConnected ? null : unauth ? 'auth_required' : rateLimited ? 'rate_limited' : 'disconnected';

        console.log(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - Final status`, {
          connected: isConnected,
          reason: finalReason,
          devicesOk: devices_ok,
          stateOk: state_ok,
          unauth,
          rateLimited,
          timestamp: new Date().toISOString()
        });

        setConnected(isConnected);
        setReason(finalReason);

      } catch (error) {
        console.error(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - Exception during polling`, error);
        if (!mounted) return;
        setHasChecked(true);
        setConnected(false);
        setReason('network_error');
      } finally {
        if (!mounted) return;
        console.log(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - Scheduling next poll in ${pollMs}ms`);
        timerRef.current = window.setTimeout(poll, pollMs);
      }
    };

    console.log('🎵 SPOTIFY STATUS HOOK: Starting initial poll', { pollMs });
    poll();
    return () => {
      mounted = false;
      if (timerRef.current) window.clearTimeout(timerRef.current);
      console.log('🎵 SPOTIFY STATUS HOOK: Cleanup completed');
    };
  }, [pollMs]);

  return { connected, reason, hasChecked } as const;
}

export function useMusicDevices(pollMs: number = 45000) {
  const [devices, setDevices] = useState<any[]>([]);
  const [hasChecked, setHasChecked] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    let mounted = true;
    let pollCount = 0;

    const poll = async () => {
      pollCount++;
      console.log(`🎵 MUSIC DEVICES HOOK: Poll #${pollCount} starting`, {
        pollMs,
        currentDevices: devices.length,
        timestamp: new Date().toISOString()
      });

      try {
        // Hard gate: don't fetch devices until auth session is ready to avoid startup stampede
        try {
          const s: any = getAuthOrchestrator().getState();
          const isAuthed = Boolean(s.is_authenticated ?? s.isAuthenticated);
          const ready = Boolean(s.session_ready ?? s.sessionReady);
          if (!(isAuthed && ready)) {
            console.warn(`🎵 MUSIC DEVICES HOOK: Poll #${pollCount} - Auth gate blocked, deferring device fetch`);
            setHasChecked(true);
            setDevices([]);
            timerRef.current = window.setTimeout(poll, pollMs);
            return;
          }
        } catch {
          // If we can't read orchestrator, avoid fetching
          console.warn(`🎵 MUSIC DEVICES HOOK: Poll #${pollCount} - Auth orchestrator unavailable, deferring device fetch`);
          setHasChecked(true);
          setDevices([]);
          timerRef.current = window.setTimeout(poll, pollMs);
          return;
        }

        console.log(`🎵 MUSIC DEVICES HOOK: Poll #${pollCount} - Calling listDevices...`);
        const resp = await listDevices();

        console.log(`🎵 MUSIC DEVICES HOOK: Poll #${pollCount} - listDevices response`, {
          response: resp,
          hasDevices: !!resp?.devices,
          devicesType: typeof resp?.devices,
          devicesLength: Array.isArray(resp?.devices) ? resp.devices.length : 'N/A',
          timestamp: new Date().toISOString()
        });

        setHasChecked(true);
        if (!mounted) {
          console.log(`🎵 MUSIC DEVICES HOOK: Poll #${pollCount} - Component unmounted, skipping update`);
          return;
        }

        const deviceList = Array.isArray(resp?.devices) ? resp.devices : [];
        console.log(`🎵 MUSIC DEVICES HOOK: Poll #${pollCount} - Setting devices`, {
          deviceCount: deviceList.length,
          devices: deviceList.map((d: any) => ({
            id: d?.id,
            name: d?.name,
            type: d?.type,
            is_active: d?.is_active
          })),
          timestamp: new Date().toISOString()
        });

        setDevices(deviceList);
      } catch (error) {
        console.error(`🎵 MUSIC DEVICES HOOK: Poll #${pollCount} - listDevices failed`, error);
        if (!mounted) return;
        setHasChecked(true);
        setDevices([]);
      } finally {
        if (!mounted) return;
        console.log(`🎵 MUSIC DEVICES HOOK: Poll #${pollCount} - Scheduling next poll in ${pollMs}ms`);
        timerRef.current = window.setTimeout(poll, pollMs);
      }
    };

    console.log('🎵 MUSIC DEVICES HOOK: Starting initial poll', { pollMs });
    poll();
    return () => {
      mounted = false;
      if (timerRef.current) window.clearTimeout(timerRef.current);
      console.log('🎵 MUSIC DEVICES HOOK: Cleanup completed');
    };
  }, [pollMs]);

  const hasDevice = devices && devices.length > 0;
  console.log('🎵 MUSIC DEVICES HOOK: Returning state', {
    deviceCount: devices.length,
    hasDevice,
    hasChecked,
    timestamp: new Date().toISOString()
  });

  return { devices, hasDevice, hasChecked } as const;
}
