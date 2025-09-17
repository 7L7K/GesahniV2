'use client';

import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';

type ReadyStatus = 'online' | 'offline';
type DepsStatus = { status: 'ok' | 'degraded'; checks: Record<string, 'ok' | 'error' | 'skipped'> } | null;

export function useBackendStatus() {
    const [ready, setReady] = useState<ReadyStatus>('offline');
    const [deps, setDeps] = useState<DepsStatus>(null);
    const [hasChecked, setHasChecked] = useState(false);
    const readyTimer = useRef<number | null>(null);
    const depsTimer = useRef<number | null>(null);
    const readyRef = useRef<ReadyStatus>('offline');

    // Keep ref in sync with state
    useEffect(() => {
        readyRef.current = ready;
    }, [ready]);

    useEffect(() => {
        let mounted = true;
        const pollReady = async () => {
            try {
                console.log('[BackendStatus] Polling /v1/health...');
                // Use AbortController instead of AbortSignal.timeout() for better browser compatibility
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 2000);

                const res = await apiFetch('/v1/health', {
                    signal: controller.signal,
                    cache: 'no-store'
                });

                clearTimeout(timeoutId);

                console.log('[BackendStatus] Response:', res.status, res.ok);

                if (!mounted) return;
                setHasChecked(true);

                const prevReady = ready;
                let newReady: ReadyStatus;

                if (res.status >= 500) {
                    console.log('[BackendStatus] 5xx status, setting offline');
                    newReady = 'offline';
                } else if (res.ok) {
                    const body = await res.json().catch(() => ({} as Record<string, unknown>));
                    console.log('[BackendStatus] Body:', body);
                    // Treat ok:false or degraded as online (degraded allowed)
                    newReady = 'online';
                } else {
                    console.log('[BackendStatus] Non-2xx but not 5xx, treating as online (degraded)');
                    newReady = 'online';
                }

                setReady(newReady);

                // Dispatch event if status changed
                const prevReadyFromRef = readyRef.current;
                if (prevReadyFromRef !== newReady && typeof window !== 'undefined') {
                    window.dispatchEvent(new CustomEvent('backend:status_changed', {
                        detail: {
                            online: newReady === 'online',
                            source: 'useBackendStatus',
                            timestamp: Date.now()
                        }
                    }));
                }
            } catch (error) {
                console.warn('[BackendStatus] Health check failed:', error);
                if (!mounted) return;

                // Handle AbortError specifically - don't treat as offline if request was aborted
                if (error instanceof Error && error.name === 'AbortError') {
                    console.log('[BackendStatus] Request aborted, not treating as offline');
                    return;
                }

                setHasChecked(true);

                // Dispatch offline event if we were previously online
                // Dispatch offline event if we were previously online
                if (readyRef.current === 'online' && typeof window !== 'undefined') {
                    window.dispatchEvent(new CustomEvent('backend:status_changed', {
                        detail: {
                            online: false,
                            source: 'useBackendStatus_error',
                            timestamp: Date.now()
                        }
                    }));
                }

                setReady('offline');
            } finally {
                if (!mounted) return;
                // Re-enable health polling for proper backend online status tracking
                readyTimer.current = window.setTimeout(pollReady, 3000);
            }
        };
        pollReady();
        return () => {
            mounted = false;
            if (readyTimer.current) clearTimeout(readyTimer.current);
        };
    }, []);

    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => {
        let mounted = true;
        const pollDeps = async () => {
            try {
                // Use AbortController instead of AbortSignal.timeout() for better browser compatibility
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 2000);

                const res = await apiFetch('/healthz/deps', {
                    signal: controller.signal,
                    cache: 'no-store'
                });

                clearTimeout(timeoutId);

                if (!mounted) return;
                if (res.ok) {
                    const body = await res.json().catch(() => null);
                    setDeps(body);
                }
            } catch (error) {
                if (!mounted) return;

                // Handle AbortError specifically - don't treat as error if request was aborted
                if (error instanceof Error && error.name === 'AbortError') {
                    console.log('[BackendStatus] Dependencies request aborted, keeping last snapshot');
                    return;
                }

                // keep last snapshot
            } finally {
                if (!mounted) return;
                // Re-enable deps polling for proper backend status tracking
                depsTimer.current = window.setTimeout(pollDeps, 10000);
            }
        };
        pollDeps();
        return () => {
            mounted = false;
            if (depsTimer.current) clearTimeout(depsTimer.current);
        };
    }, []);

    return { ready, deps, hasChecked };
}

export type { ReadyStatus, DepsStatus };
