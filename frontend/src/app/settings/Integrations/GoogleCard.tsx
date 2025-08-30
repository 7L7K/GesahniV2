'use client';

import { useEffect, useState } from 'react';
import { getGoogleStatus, connectGoogle, disconnectGoogle } from '@/lib/api/integrations';
import { toast } from '@/lib/toast';

export default function GoogleCard({ onManage }: { onManage?: () => void }) {
    const [status, setStatus] = useState<'not_connected' | 'connecting' | 'connected' | 'error'>('not_connected');
    const [scopes, setScopes] = useState<string[]>([]);
    const [expiresAt, setExpiresAt] = useState<number | null>(null);

    const hasGmailScope = (s: string[]) => s.some(x => x.includes('gmail.') || x.endsWith('/gmail.send') || x.endsWith('/gmail.readonly'));
    const hasCalendarScope = (s: string[]) => s.some(x => x.includes('calendar.') || x.endsWith('/calendar.events') || x.endsWith('/calendar.readonly'));

    const fetchStatus = async () => {
        try {
            const j = await getGoogleStatus();
            if (j.connected) {
                setStatus('connected');
                setScopes(Array.isArray(j.scopes) ? j.scopes : []);
                setExpiresAt(j.expires_at || null);
            } else {
                setStatus(j.degraded_reason ? 'error' : 'not_connected');
                setScopes(Array.isArray(j.scopes) ? j.scopes : []);
            }
        } catch (e: any) {
            console.error('Failed to fetch google status', e);
            setStatus('error');
        }
    };

    useEffect(() => {
        fetchStatus();

        // Hash handler
        if (typeof window !== 'undefined') {
            const h = window.location.hash;
                if (h.startsWith('#google=connected')) {
                    toast.success('Google connected');
                    history.replaceState({}, '', window.location.pathname + window.location.search);
                    fetchStatus();
                }
                // Optionally show per-service health banner from /v1/health/google
                (async () => {
                    try {
                        const health = await fetch('/v1/health/google', { credentials: 'include' });
                        if (health.ok) {
                            const j = await health.json();
                            // If service reports errors, show small notice
                            const svc = j.services || {};
                            if (svc.gmail && svc.gmail.status === 'error') {
                                toast.warning(`Gmail: ${svc.gmail.last_error?.code || 'error'}`);
                            }
                            if (svc.calendar && svc.calendar.status === 'error') {
                                toast.warning(`Calendar: ${svc.calendar.last_error?.code || 'error'}`);
                            }
                        }
                    } catch (e) { }
                })();
            if (h.startsWith('#google=error:')) {
                const code = h.split(':')[1] || 'error';
                toast.error(`Google connection failed: ${code}`);
                history.replaceState({}, '', window.location.pathname + window.location.search);
            }
        }
    }, []);

    const handleConnect = async () => {
        setStatus('connecting');
        try {
            const data = await connectGoogle();
            const url = data?.authorize_url;
            if (url) window.location.href = url;
            else fetchStatus();
        } catch (e: any) {
            toast.error('Failed to open Google consent');
            setStatus('not_connected');
        }
    };

    const handleDisconnect = async () => {
        if (!confirm('Disconnect Google? Gmail/Calendar features will stop working until you reconnect.')) return;
        try {
            await disconnectGoogle();
            toast.success('Google disconnected');
            fetchStatus();
        } catch (e: any) {
            toast.error('Failed to disconnect Google');
        }
    };

    return (
        <div className="border rounded-lg p-6">
            <div className="flex items-start justify-between">
                <div>
                    <h3 className="text-lg font-medium">Google</h3>
                    <p className="text-sm text-gray-600 mt-1">Allow Gesahni to read Gmail & Calendar to power smart alerts and scheduling.</p>
                </div>
                <div>
                    {status === 'connected' && <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">🟢 Connected</span>}
                    {status === 'not_connected' && <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800">⚪ Not connected</span>}
                    {status === 'connecting' && <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">🟡 Connecting…</span>}
                    {status === 'error' && <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-800">🟠 Error</span>}
                </div>
            </div>

            <div className="mt-4">
                {status === 'not_connected' && (
                    <div className="space-y-2">
                        <p className="text-sm text-gray-600">Allow Gesahni to read Gmail & Calendar to power smart alerts and scheduling.</p>
                        <div className="flex items-center space-x-2">
                            <button className="bg-blue-600 text-white px-4 py-2 rounded" onClick={handleConnect}>Connect with Google</button>
                            <button className="text-sm underline" onClick={() => alert("What you'll get: Gmail read, Calendar read; revoke anytime in Google Account.")}>What you'll get</button>
                        </div>
                    </div>
                )}

                {status === 'connecting' && (
                    <div className="flex items-center space-x-2">
                        <div className="animate-spin w-4 h-4 border-2 border-gray-300 border-t-transparent rounded-full" />
                        <span>Opening Google…</span>
                    </div>
                )}

                {status === 'connected' && (
                    <div>
                        <div className="text-sm text-gray-600">Last checked: {expiresAt ? new Date(expiresAt * 1000).toLocaleString() : '—'}</div>
                        <div className="mt-2 flex space-x-2">
                            {hasGmailScope(scopes) && <span className="px-2 py-1 bg-gray-100 rounded text-xs">Gmail</span>}
                            {hasCalendarScope(scopes) && <span className="px-2 py-1 bg-gray-100 rounded text-xs">Calendar</span>}
                        </div>
                        <div className="mt-4 flex space-x-2">
                            <button className="px-3 py-2 border rounded" onClick={() => onManage?.()}>Manage</button>
                            <button className="px-3 py-2 text-red-600 border rounded" onClick={handleDisconnect}>Disconnect</button>
                        </div>
                        {scopes?.length > 0 && (
                            <div className="mt-3 text-xs text-gray-500 break-words">Scopes: {scopes.join(' ')}</div>
                        )}
                    </div>
                )}

                {status === 'error' && (
                    <div>
                        <p className="text-sm text-amber-800">Session expired. Re-connect to continue.</p>
                        <div className="mt-2">
                            <button className="bg-blue-600 text-white px-4 py-2 rounded" onClick={handleConnect}>Reconnect</button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
