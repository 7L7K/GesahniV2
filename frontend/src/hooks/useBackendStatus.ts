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

    useEffect(() => {
        let mounted = true;
        const pollReady = async () => {
            try {
                console.log('[BackendStatus] Polling /healthz/ready...');
                // Use AbortController instead of AbortSignal.timeout() for better browser compatibility
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 2000);

                const res = await apiFetch('/healthz/ready', {
                    signal: controller.signal,
                    cache: 'no-store',
                    credentials: 'include'
                });

                clearTimeout(timeoutId);

                console.log('[BackendStatus] Response:', res.status, res.ok);

                if (!mounted) return;
                setHasChecked(true);
                if (res.ok) {
                    const body = await res.json().catch(() => ({} as Record<string, unknown>));
                    console.log('[BackendStatus] Body:', body);
                    setReady(body?.status === 'ok' ? 'online' : 'offline');
                } else {
                    console.log('[BackendStatus] Response not ok, setting offline');
                    setReady('offline');
                }
            } catch (error) {
                console.log('[BackendStatus] Error:', error);
                if (!mounted) return;

                // Handle AbortError specifically - don't treat as offline if request was aborted
                if (error instanceof Error && error.name === 'AbortError') {
                    console.log('[BackendStatus] Request aborted, not treating as offline');
                    return;
                }

                setHasChecked(true);
                setReady('offline');
            } finally {
                if (!mounted) return;
                // DISABLED: Health polling should be controlled by orchestrator
                // readyTimer.current = window.setTimeout(pollReady, 3000);
            }
        };
        pollReady();
        return () => {
            mounted = false;
            if (readyTimer.current) clearTimeout(readyTimer.current);
        };
    }, []);

    useEffect(() => {
        let mounted = true;
        const pollDeps = async () => {
            try {
                // Use AbortController instead of AbortSignal.timeout() for better browser compatibility
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 2000);

                const res = await apiFetch('/healthz/deps', {
                    signal: controller.signal,
                    cache: 'no-store',
                    credentials: 'include'
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
                // DISABLED: Health polling should be controlled by orchestrator
                // depsTimer.current = window.setTimeout(pollDeps, 10000);
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


