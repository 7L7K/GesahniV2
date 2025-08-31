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
        const s = getAuthOrchestrator().getState();
        const isAuthed = Boolean(s.is_authenticated);
        const ready = Boolean(s.session_ready);
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

      let isConnected = false;
      let finalReason: string | null = null;
      let rateLimited = false;

      try {
        console.log(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - Checking status...`);

        // Use the dedicated status endpoint instead of polling live endpoints
        const statusResponse = await apiFetch('/v1/spotify/status', {
          auth: true,
          dedupe: false,
          cache: 'no-store'
        });

        console.log(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - Status endpoint response`, {
          ok: statusResponse.ok,
          status: statusResponse.status,
          statusText: statusResponse.statusText,
          timestamp: new Date().toISOString()
        });

        setHasChecked(true);
        if (!mounted) {
          console.log(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - Component unmounted, skipping update`);
          return;
        }

        if (statusResponse.ok) {
          const statusData = await statusResponse.json();
          console.log(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - Status data received`, {
            connected: statusData.connected,
            devices_ok: statusData.devices_ok,
            state_ok: statusData.state_ok,
            reason: statusData.reason,
            required_scopes_ok: statusData.required_scopes_ok,
            scopes: statusData.scopes,
            timestamp: new Date().toISOString()
          });

          isConnected = statusData.connected;
          finalReason = isConnected ? null : statusData.reason || 'disconnected';
        } else {
          // Status endpoint failed
          console.error(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - Status endpoint failed`, {
            status: statusResponse.status,
            statusText: statusResponse.statusText
          });
          isConnected = false;
          finalReason = 'disconnected';
        }

        setConnected(isConnected);
        setReason(finalReason);

      } catch (error) {
        console.error(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - Exception during polling`, error);
        if (!mounted) return;
        setHasChecked(true);
        setConnected(false);
        setReason('network_error');
        isConnected = false;
        finalReason = 'network_error';
      } finally {
        if (!mounted) return;

        // Don't continue polling if we have a stable state that doesn't need monitoring
        // Only stop polling for truly stable states (connected or needs OAuth setup)
        const shouldStopPolling = finalReason === 'needs_spotify_connect' ||
          (isConnected && !rateLimited);

        if (shouldStopPolling) {
          console.log(`🎵 SPOTIFY STATUS HOOK: Poll #${pollCount} - Stopping polling, stable state: ${finalReason || 'connected'}`);
          return;
        }

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

  // Listen for auth state changes to trigger immediate polling when session becomes ready
  useEffect(() => {
    const handleAuthStateChange = (event: Event) => {
      const customEvent = event as CustomEvent;
      const detail = customEvent.detail;
      // If session became ready and we're authenticated, trigger immediate poll
      if (!detail.prevState.session_ready && detail.newState.session_ready && detail.newState.is_authenticated) {
        console.info('🎵 SPOTIFY STATUS HOOK: Session became ready, triggering immediate poll');
        // Clear any pending timer and trigger immediate poll
        if (timerRef.current) {
          clearTimeout(timerRef.current);
          timerRef.current = null;
        }
        // Small delay to ensure auth propagation
        setTimeout(() => {
          if (timerRef.current === null) { // Only if not already triggered
            // This will trigger the poll function from the main useEffect
            window.dispatchEvent(new CustomEvent('spotify:force_poll'));
          }
        }, 100);
      }
    };

    window.addEventListener('auth:state_changed', handleAuthStateChange);
    return () => window.removeEventListener('auth:state_changed', handleAuthStateChange);
  }, []);

  return { connected, reason, hasChecked } as const;
}

export function useMusicDevices(pollMs: number = 45000) {
  const [devices, setDevices] = useState<unknown[]>([]);
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

      let resp: any = null;
      try {
        // Hard gate: don't fetch devices until auth session is ready to avoid startup stampede
        try {
          const s = getAuthOrchestrator().getState();
          const isAuthed = Boolean(s.is_authenticated);
          const ready = Boolean(s.session_ready);
          if (!(isAuthed && ready)) {
            console.warn(`🎵 MUSIC DEVICES HOOK: Poll #${pollCount} - Auth gate blocked, deferring device fetch`);
            setHasChecked(true);
            setDevices([]);
            timerRef.current = window.setTimeout(poll, pollMs);
            return;
          }
        } catch (error) {
          // If we can't read orchestrator, avoid fetching
          console.warn(`🎵 MUSIC DEVICES HOOK: Poll #${pollCount} - Auth orchestrator unavailable, deferring device fetch`, error);
          setHasChecked(true);
          setDevices([]);
          timerRef.current = window.setTimeout(poll, pollMs);
          return;
        }

        console.log(`🎵 MUSIC DEVICES HOOK: Poll #${pollCount} - Calling listDevices...`);
        resp = await listDevices();

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

        // Check if we got a spotify_not_authenticated error
        if (resp?.error?.code === 'spotify_not_authenticated') {
          console.log(`🎵 MUSIC DEVICES HOOK: Poll #${pollCount} - Spotify not connected, stopping polling`);
          setDevices([]);
          // Don't schedule next poll for this stable state
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

        // Don't continue polling only for definitive stable states
        // Stop polling if Spotify is not authenticated (user needs to connect)
        // Keep polling if no devices found (devices might become available)
        const hasStableState = resp?.error?.code === 'spotify_not_authenticated';

        if (hasStableState) {
          console.log(`🎵 MUSIC DEVICES HOOK: Poll #${pollCount} - Stopping polling, stable state`);
          return;
        }

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

  // Listen for auth state changes to trigger immediate polling when session becomes ready
  useEffect(() => {
    const handleAuthStateChange = (event: Event) => {
      const customEvent = event as CustomEvent;
      const detail = customEvent.detail;
      // If session became ready and we're authenticated, trigger immediate poll
      if (!detail.prevState.session_ready && detail.newState.session_ready && detail.newState.is_authenticated) {
        console.info('🎵 MUSIC DEVICES HOOK: Session became ready, triggering immediate poll');
        // Clear any pending timer and trigger immediate poll
        if (timerRef.current) {
          clearTimeout(timerRef.current);
          timerRef.current = null;
        }
        // Small delay to ensure auth propagation
        setTimeout(() => {
          if (timerRef.current === null) { // Only if not already triggered
            // This will trigger the poll function from the main useEffect
            window.dispatchEvent(new CustomEvent('music_devices:force_poll'));
          }
        }, 100);
      }
    };

    window.addEventListener('auth:state_changed', handleAuthStateChange);
    return () => window.removeEventListener('auth:state_changed', handleAuthStateChange);
  }, []);

  const hasDevice = devices && devices.length > 0;
  console.log('🎵 MUSIC DEVICES HOOK: Returning state', {
    deviceCount: devices.length,
    hasDevice,
    hasChecked,
    timestamp: new Date().toISOString()
  });

  return { devices, hasDevice, hasChecked } as const;
}
