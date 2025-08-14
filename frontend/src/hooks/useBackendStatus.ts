'use client';

import { useEffect, useRef, useState } from 'react';

type ReadyStatus = 'online' | 'offline';
type DepsStatus = { status: 'ok' | 'degraded'; checks: Record<string, 'ok' | 'error' | 'skipped'> } | null;

export function useBackendStatus() {
    const [ready, setReady] = useState<ReadyStatus>('offline');
    const [deps, setDeps] = useState<DepsStatus>(null);
    const readyTimer = useRef<number | null>(null);
    const depsTimer = useRef<number | null>(null);

    useEffect(() => {
        let mounted = true;
        const pollReady = async () => {
            try {
                const ctrl = AbortSignal.timeout(2000);
                const res = await fetch('/healthz/ready', { credentials: 'omit', cache: 'no-store', signal: ctrl });
                if (!mounted) return;
                if (res.ok) {
                    const body = await res.json().catch(() => ({} as any));
                    setReady(body?.status === 'ok' ? 'online' : 'offline');
                } else {
                    setReady('offline');
                }
            } catch {
                if (!mounted) return;
                setReady('offline');
            } finally {
                if (!mounted) return;
                readyTimer.current = window.setTimeout(pollReady, 3000);
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
                const ctrl = AbortSignal.timeout(2000);
                const res = await fetch('/healthz/deps', { credentials: 'omit', cache: 'no-store', signal: ctrl });
                if (!mounted) return;
                if (res.ok) {
                    const body = await res.json().catch(() => null);
                    setDeps(body);
                }
            } catch {
                if (!mounted) return;
                // keep last snapshot
            } finally {
                if (!mounted) return;
                depsTimer.current = window.setTimeout(pollDeps, 10000);
            }
        };
        pollDeps();
        return () => {
            mounted = false;
            if (depsTimer.current) clearTimeout(depsTimer.current);
        };
    }, []);

    return { ready, deps };
}

export type { ReadyStatus, DepsStatus };


