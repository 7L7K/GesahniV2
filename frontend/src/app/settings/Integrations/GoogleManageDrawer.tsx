'use client';

import { useEffect, useState } from 'react';
import { getGoogleStatus, connectGoogle, disconnectGoogle } from '@/lib/api/integrations';
import { toast } from '@/lib/toast';

export default function GoogleManageDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
    const [gmailOk, setGmailOk] = useState<boolean | null>(null);
    const [calOk, setCalOk] = useState<boolean | null>(null);
    const [scopes, setScopes] = useState<string[]>([]);

    const hasGmailScope = (s: string[]) => s.some(x => x.includes('gmail.') || x.endsWith('/gmail.send') || x.endsWith('/gmail.readonly'));
    const hasCalendarScope = (s: string[]) => s.some(x => x.includes('calendar.') || x.endsWith('/calendar.events') || x.endsWith('/calendar.readonly'));

    useEffect(() => {
        if (!open) return;
        (async () => {
            try {
                const s = await getGoogleStatus();
                const sc: string[] = Array.isArray(s.scopes) ? s.scopes : [];
                setScopes(sc);
                setGmailOk(hasGmailScope(sc));
                setCalOk(hasCalendarScope(sc));
            } catch (e) {
                setGmailOk(false); setCalOk(false);
            }
        })();
    }, [open]);

    const handleReauth = async () => {
        try {
            const data = await connectGoogle();
            const url = data?.authorize_url;
            if (url) window.location.href = url;
        } catch (e) { toast.error('Failed to start re-auth'); }
    };

    const handleDisconnect = async () => {
        if (!confirm('Disconnect Google? Gmail/Calendar features will stop working until you reconnect.')) return;
        try { await disconnectGoogle(); toast.success('Disconnected'); onClose(); } catch { toast.error('Disconnect failed'); }
    };

    return (
        <div className={`fixed right-0 top-0 h-full w-96 bg-white shadow-xl transform ${open ? 'translate-x-0' : 'translate-x-full'} transition-transform`}>
            <div className="p-6">
                <div className="flex items-center justify-between">
                    <h3 className="text-lg font-medium">Google Manage</h3>
                    <button onClick={onClose}>Close</button>
                </div>

                <div className="mt-4 space-y-4">
                    <div>
                        <div className="flex items-center justify-between">
                            <div>
                                <div className="font-medium">Gmail access</div>
                                <div className="text-sm text-gray-600">
                                    Capabilities: {scopes.some(s=>s.endsWith('/gmail.send')) ? 'Send email' : scopes.some(s=>s.endsWith('/gmail.readonly')) ? 'Read email' : '—'}
                                </div>
                            </div>
                            <div>{gmailOk === null ? '…' : gmailOk ? '✅' : '❌'}</div>
                        </div>
                    </div>

                    <div>
                        <div className="flex items-center justify-between">
                            <div>
                                <div className="font-medium">Calendar access</div>
                                <div className="text-sm text-gray-600">
                                    Capabilities: {scopes.some(s=>s.endsWith('/calendar.events')) ? 'Create events' : scopes.some(s=>s.endsWith('/calendar.readonly')) ? 'Read events' : '—'}
                                </div>
                            </div>
                            <div>{calOk === null ? '…' : calOk ? '✅' : '❌'}</div>
                        </div>
                    </div>

                    <div className="space-x-2">
                        <button className="px-4 py-2 bg-blue-600 text-white rounded" onClick={handleReauth}>Re-authorize</button>
                        <button className="px-4 py-2 border rounded text-red-600" onClick={handleDisconnect}>Disconnect</button>
                    </div>
                </div>
                {scopes.length>0 && (
                    <div className="mt-4 text-xs text-gray-500 break-words">Scopes: {scopes.join(' ')}</div>
                )}
            </div>
        </div>
    );
}
