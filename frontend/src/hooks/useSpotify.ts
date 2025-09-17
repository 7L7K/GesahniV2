'use client';

import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { getAuthOrchestrator } from '@/services/authOrchestrator';
import { listDevices, fetchDevices, fetchSpotifyStatus } from '@/lib/api';
import { FEATURES } from '@/config/features';

export function useSpotifyStatus(pollMs: number = 30000) {
  const [connected, setConnected] = useState<boolean>(false);
  const [reason, setReason] = useState<string | null>(null);
  const [hasChecked, setHasChecked] = useState<boolean>(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    // Check feature flag - if music devices polling is disabled, don't start Spotify status polling either
    if (!FEATURES.MUSIC_DEVICES_POLL_ENABLED) {
      console.info("music.poll:disabled", {
        reason: "feature_flag_disabled",
        timestamp: new Date().toISOString(),
        hook: "useSpotifyStatus"
      });
      setConnected(false);
      setReason('feature_disabled');
      setHasChecked(true);
      return;
    }

    let mounted = true;
    let pollCount = 0;

    const poll = async () => {
      pollCount++;
      // Log first poll start
      if (pollCount === 1) {
        console.info("music.poll:start", {
          pollMs,
          timestamp: new Date().toISOString(),
          hook: "useSpotifyStatus"
        });
      }
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
          // Log poll stop with reason
          console.info("music.poll:stop", {
            reason: finalReason || 'connected',
            pollCount,
            timestamp: new Date().toISOString(),
            hook: "useSpotifyStatus"
          });
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

    const handleStopPolling = (event: Event) => {
      const customEvent = event as CustomEvent;
      const detail = customEvent.detail;
      console.info('🎵 SPOTIFY STATUS HOOK: Received stop polling event', { reason: detail?.reason });

      // Clear any pending timer
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }

      // Update state to indicate polling stopped
      setConnected(false);
      setReason('auth_expired');
      setHasChecked(true);

      // Log poll stop
      console.info("music.poll:stop", {
        reason: 'auth_expired',
        timestamp: new Date().toISOString(),
        hook: "useSpotifyStatus"
      });
    };

    window.addEventListener('auth:state_changed', handleAuthStateChange);
    window.addEventListener('auth:stop_polling', handleStopPolling);
    window.addEventListener('auth:stop_all_polling', handleStopPolling);

    return () => {
      window.removeEventListener('auth:state_changed', handleAuthStateChange);
      window.removeEventListener('auth:stop_polling', handleStopPolling);
      window.removeEventListener('auth:stop_all_polling', handleStopPolling);
    };
  }, []);

  return { connected, reason, hasChecked } as const;
}

export function useMusicDevices() {
  const [devices, setDevices] = useState<any[]>([]);
  const [connected, setConnected] = useState<boolean>(false);
  const timer = useRef<any>(null);

  // exponential backoff state
  const backoffRef = useRef<number>(15000); // 15s baseline

  useEffect(() => {
    // Check feature flag - if disabled, don't start polling
    if (!FEATURES.MUSIC_DEVICES_POLL_ENABLED) {
      console.info("music.poll:disabled", {
        reason: "feature_flag_disabled",
        timestamp: new Date().toISOString(),
        hook: "useMusicDevices"
      });
      setDevices([]);
      setConnected(false);
      return;
    }

    let cancelled = false;

    async function checkStatusThenPoll() {
      const status = await fetchSpotifyStatus(); // should request with cache: "no-store"
      if (cancelled) return;
      setConnected(Boolean(status?.connected));
      if (!status?.connected) {
        // ensure no poll is running
        if (timer.current) clearTimeout(timer.current);
        // Log poll stop
        console.info("music.poll:stop", {
          reason: "not_connected",
          timestamp: new Date().toISOString(),
          hook: "useMusicDevices"
        });
        return;
      }

      async function poll() {
        // Log first poll start
        if (!timer.current) {
          console.info("music.poll:start", {
            timestamp: new Date().toISOString(),
            hook: "useMusicDevices"
          });
        }

        try {
          const resp = await apiFetch('/v1/music/devices', { auth: true, dedupe: false, cache: 'no-store' });
          if (cancelled) return;
          const data = await resp.json().catch(() => ({ devices: [] }));
          setDevices(data.devices ?? []);
          backoffRef.current = 15000; // reset backoff on success
        } catch (err: any) {
          if (err?.code === "spotify_not_authenticated") {
            // stop polling entirely; gate will re-open if status flips
            if (timer.current) clearTimeout(timer.current);
            setConnected(false);
            // Log poll stop
            console.info("music.poll:stop", {
              reason: "spotify_not_authenticated",
              timestamp: new Date().toISOString(),
              hook: "useMusicDevices"
            });
            return;
          }
          // Backoff for transient failures (429/5xx)
          backoffRef.current = Math.min(backoffRef.current * 1.6, 180000); // cap 3 min
        } finally {
          const wait = backoffRef.current;
          timer.current = setTimeout(poll, wait);
        }
      }

      poll();
    }

    checkStatusThenPoll();
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  return { devices, connected };
}
