'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { toast } from '@/lib/toast';
import {
    ShieldCheck,
    ShieldAlert,
    Loader2,
    Mail,
    Calendar,
    Settings2,
    PlugZap,
    Power,
    RefreshCw,
    ExternalLink,
} from 'lucide-react';

/**
 * GoogleConnectCard.tsx – v4 (adapts to your current API wrappers)
 *
 * This version uses your helpers from `@/lib/api/integrations`:
 *   getGoogleStatus(): Promise<{ connected?: boolean, scopes?: string[], expires_at?: number, degraded_reason?: string }>
 *   connectGoogle(): Promise<{ authorize_url?: string }>
 *   disconnectGoogle(): Promise<{ ok?: boolean }>
 *
 * Key changes:
 *  - Defensive fetch with AbortController to prevent state after unmount
 *  - Normalizes your payload (connected/scopes/expires_at)
 *  - Hash-handling (#google=connected|error:CODE) stays but is hardened
 *  - Popup-less by default (your connect returns an authorize_url → we hard redirect for now)
 *  - Testable helper `normalizeFromApi`
 */

import { getGoogleStatus, connectGoogle, disconnectGoogle } from '@/lib/api/integrations';

export type UiStatus = 'not_connected' | 'connecting' | 'connected' | 'error' | 'loading';

export type Normalized = {
    connected: boolean;
    requiredScopesOk?: boolean;
    scopes: string[];
    expiresAt?: number | null; // epoch seconds
};

export function normalizeFromApi(j: any): Normalized {
    const connected = Boolean(j?.connected);
    const requiredScopesOk = typeof j?.required_scopes_ok === 'boolean' ? j.required_scopes_ok : undefined;
    const scopes = Array.isArray(j?.scopes) ? j.scopes.filter((s: any) => typeof s === 'string') : [];
    const expiresAt = typeof j?.expires_at === 'number' && isFinite(j.expires_at) ? j.expires_at : null;
    return { connected, requiredScopesOk, scopes, expiresAt };
}

export default function GoogleConnectCard({ onManage }: { onManage?: () => void }) {
    const [status, setStatus] = useState<UiStatus>('loading');
    const [scopes, setScopes] = useState<string[]>([]);
    const [expiresAt, setExpiresAt] = useState<number | null>(null);
    const [requiredScopesOk, setRequiredScopesOk] = useState<boolean | undefined>(undefined);
    const inflight = useRef<AbortController | null>(null);

    const hasGmailScope = useCallback((s: string[]) => s.some(x => x.includes('gmail.') || x.endsWith('/gmail.send') || x.endsWith('/gmail.readonly')), []);
    const hasCalendarScope = useCallback((s: string[]) => s.some(x => x.includes('calendar.') || x.endsWith('/calendar.events') || x.endsWith('/calendar.readonly')), []);

    const clearHash = useCallback(() => {
        if (typeof window === 'undefined') return;
        const { pathname, search } = window.location;
        history.replaceState({}, '', pathname + search);
    }, []);

    async function fetchStatus(silent = false) {
        // cancel previous request
        inflight.current?.abort();
        const controller = new AbortController();
        inflight.current = controller;

        try {
            if (!silent) setStatus('loading');
            const j = await getGoogleStatus();
            const n = normalizeFromApi(j);
            setScopes(n.scopes);
            setExpiresAt(n.expiresAt ?? null);
            setRequiredScopesOk(n.requiredScopesOk);
            setStatus(n.connected ? 'connected' : (j?.degraded_reason ? 'error' : 'not_connected'));
            return n.connected;
        } catch (e: any) {
            if (e?.name === 'AbortError') return false;
            console.error('Failed to fetch google status', e);
            setStatus('error');
            return false;
        }
    }

    useEffect(() => {
        fetchStatus();

        // Hash handler + optional per-service health banner
        if (typeof window !== 'undefined') {
            const h = window.location.hash || '';
            (async () => {
                if (h.startsWith('#google=connected')) {
                    toast.success('Google connected');
                    clearHash();
                    await fetchStatus(true);
                } else if (h.startsWith('#google=error:')) {
                    const code = h.split(':')[1] || 'error';
                    toast.error(`Google connection failed: ${code}`);
                    clearHash();
                }

                try {
                    const apiUrl = `${process.env.NEXT_PUBLIC_API_ORIGIN || 'http://localhost:8000'}/v1/health/google`;
                    console.log('🔗 GoogleCard: Making health request to:', apiUrl);
                    const health = await fetch(apiUrl, { credentials: 'include' });
                    console.log('🔗 GoogleCard: Health response status:', health.status, 'ok:', health.ok);
                    if (health.ok) {
                        const j = await health.json();
                        console.log('🔗 GoogleCard: Health response data:', j);
                        const svc = j?.services || {};
                        if (svc.gmail?.status === 'error') toast.warning(`Gmail: ${svc.gmail?.last_error?.code || 'error'}`);
                        if (svc.calendar?.status === 'error') toast.warning(`Calendar: ${svc.calendar?.last_error?.code || 'error'}`);
                    } else {
                        console.error('🔗 GoogleCard: Health request failed with status:', health.status);
                    }
                } catch (e) {
                    console.error('🔗 GoogleCard: Health request error:', e);
                }
            })();
        }

        return () => inflight.current?.abort();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    async function handleConnect() {
        console.log('🔗 GoogleCard: handleConnect called');
        setStatus('connecting');
        try {
            console.log('🔗 GoogleCard: Calling connectGoogle...');
            const data = await connectGoogle();
            console.log('🔗 GoogleCard: connectGoogle returned:', data);
            console.log('🔗 GoogleCard: Full response object:', JSON.stringify(data, null, 2));

            const url = data?.authorize_url; // support either key
            console.log('🔗 GoogleCard: Extracted URL:', url);

            if (typeof url === 'string' && url.length > 0) {
                console.log('🔗 GoogleCard: Redirecting to:', url);
                window.location.href = url;
            } else {
                console.log('🔗 GoogleCard: No valid URL, refreshing status');
                // If backend already linked (rare), just refresh the status
                await fetchStatus();
            }
        } catch (e: any) {
            console.error('🔗 GoogleCard: connectGoogle failed', e);
            console.error('🔗 GoogleCard: Error details:', JSON.stringify(e, null, 2));
            console.error('🔗 GoogleCard: Error message:', e.message);
            console.error('🔗 GoogleCard: Error stack:', e.stack);

            // Show the actual error message if available
            const errorMsg = e.message || 'Failed to open Google consent';
            toast.error(errorMsg);
            setStatus('not_connected');
        }
    }

    async function handleDisconnect() {
        if (!confirm('Disconnect Google? Gmail/Calendar features will stop working until you reconnect.')) return;
        try {
            await disconnectGoogle();
            toast.success('Google disconnected');
            await fetchStatus();
        } catch (e: any) {
            console.error('disconnectGoogle failed', e);
            toast.error('Failed to disconnect Google');
        }
    }

    const friendlyBadges = useMemo(() => {
        const pretty: Record<string, string> = {
            'https://www.googleapis.com/auth/gmail.readonly': 'Gmail (read)',
            'https://www.googleapis.com/auth/gmail.modify': 'Gmail (modify)',
            'https://www.googleapis.com/auth/calendar.readonly': 'Calendar (read)',
            'https://www.googleapis.com/auth/calendar': 'Calendar (rw)',
            openid: 'OpenID',
            email: 'Email',
            profile: 'Profile',
        };
        return scopes.map(s => (
            <Badge key={s} variant="secondary" className="mr-2 mt-2" data-testid={`scope-${s}`}>
                {pretty[s] ?? s.replace('https://www.googleapis.com/auth/', '')}
            </Badge>
        ));
    }, [scopes]);

    const expiresLabel = useMemo(() => (expiresAt ? new Date(expiresAt * 1000).toLocaleString() : '—'), [expiresAt]);

    return (
        <Card className="border border-neutral-800 bg-neutral-950 text-neutral-50" data-testid="google-card">
            <CardContent className="p-5">
                <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
                    <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-2xl bg-neutral-800 grid place-items-center">
                            <PlugZap className="h-5 w-5" />
                        </div>
                        <div>
                            <div className="flex items-center gap-2">
                                <h3 className="text-lg font-semibold">Google</h3>
                                {status === 'loading' ? (
                                    <Skeleton className="h-5 w-24" />
                                ) : status === 'connected' ? (
                                    requiredScopesOk === false ? (
                                        <Badge variant="secondary" className="bg-yellow-600" data-testid="status-connected-limited">Connected (limited) ⚠️</Badge>
                                    ) : (
                                        <Badge variant="default" className="bg-emerald-600" data-testid="status-connected">Connected ✅</Badge>
                                    )
                                ) : status === 'connecting' ? (
                                    <Badge variant="secondary" className="bg-yellow-600/30" data-testid="status-connecting">Connecting…</Badge>
                                ) : status === 'error' ? (
                                    <Badge variant="destructive" className="bg-amber-600" data-testid="status-error">Error</Badge>
                                ) : (
                                    <Badge variant="destructive" className="bg-rose-600" data-testid="status-disconnected">Not connected</Badge>
                                )}
                            </div>
                            <p className="text-sm text-neutral-400 mt-1">Read-only Gmail & Calendar for smart alerts and scheduling.</p>

                            {status !== 'loading' && (
                                <div className="mt-2 text-sm text-neutral-400 space-y-1">
                                    <div className="flex items-center gap-2 min-h-[24px]">
                                        <Avatar className="h-5 w-5"><AvatarFallback className="text-[10px]">G</AvatarFallback></Avatar>
                                        <Mail className="h-4 w-4" />
                                        <span>{status === 'connected' ? 'Linked' : 'No account linked'}</span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <Calendar className="h-4 w-4" />
                                        <span>Last checked: {expiresLabel}</span>
                                    </div>
                                    {scopes?.length > 0 && <div className="flex flex-wrap items-center pt-1">{friendlyBadges}</div>}
                                </div>
                            )}
                        </div>
                    </div>

                    <div className="flex items-center gap-2 self-start">
                        {status === 'loading' ? (
                            <Loader2 className="h-5 w-5 animate-spin" />
                        ) : status === 'connected' ? (
                            <>
                                <Button variant="secondary" className="gap-2" onClick={() => fetchStatus(true)} data-testid="btn-refresh">
                                    <RefreshCw className="h-4 w-4" />
                                    Check
                                </Button>
                                <Button variant="secondary" className="gap-2" onClick={() => onManage?.()} data-testid="btn-manage">
                                    <Settings2 className="h-4 w-4" />
                                    Manage
                                </Button>
                                <Button variant="destructive" className="gap-2" onClick={handleDisconnect} data-testid="btn-disconnect">
                                    <Power className="h-4 w-4" />
                                    Disconnect
                                </Button>
                            </>
                        ) : status === 'connecting' ? (
                            <Loader2 className="h-5 w-5 animate-spin" />
                        ) : (
                            <Button
                                onClick={() => {
                                    console.log('🔗 GoogleCard: Button clicked!');
                                    handleConnect();
                                }}
                                className="gap-2"
                                data-testid="btn-connect"
                            >
                                <ShieldCheck className="h-4 w-4" />
                                Connect with Google
                            </Button>
                        )}
                    </div>
                </div>

                {status !== 'connected' && status !== 'loading' && (
                    <div className="mt-4 text-sm text-neutral-400 flex items-start gap-2">
                        <ShieldAlert className="h-4 w-4 mt-0.5" />
                        <p>Requests read-only scopes by default. You can elevate access in Admin → Integrations → Google.</p>
                    </div>
                )}

                <div className="mt-3 text-xs text-neutral-500 flex items-center gap-1">
                    <ExternalLink className="h-3 w-3" />
                    <span>Need help? See Admin → Integrations → Google setup.</span>
                </div>
            </CardContent>
        </Card>
    );
}

/* -------------------------------------------------
   TESTS (Vitest)
--------------------------------------------------*/
// @vitest-environment jsdom
// Uncomment the following block when using Vitest
/*
if (typeof import !== 'undefined' && (import.meta as any)?.vitest) {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { describe, it, expect } = (import.meta as any).vitest;

  describe('normalizeFromApi', () => {
    it('handles empty payload', () => {
      const n = normalizeFromApi({});
      expect(n.connected).toBe(false);
      expect(n.scopes).toEqual([]);
      expect(n.expiresAt).toBe(null);
    });

    it('parses valid payload', () => {
      const n = normalizeFromApi({ connected: true, scopes: ['a','b'], expires_at: 1712000000 });
      expect(n.connected).toBe(true);
      expect(n.scopes).toEqual(['a','b']);
      expect(n.expiresAt).toBe(1712000000);
    });

    it('filters bad scopes and coerces expires', () => {
      const n = normalizeFromApi({ connected: 1, scopes: ['ok', 2, null], expires_at: 'nope' });
      expect(n.connected).toBe(true);
      expect(n.scopes).toEqual(['ok']);
      expect(n.expiresAt).toBe(null);
    });
  });
}
*/
