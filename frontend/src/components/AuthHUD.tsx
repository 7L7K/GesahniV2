'use client';
import { useEffect, useState } from 'react';

export default function AuthHud() {
    const [state, setState] = useState<any>(null);
    const [whoami, setWhoami] = useState<any>(null);

    useEffect(() => {
        (async () => {
            // hit a cheap endpoint to read diagnostic headers
            const r = await fetch('/v1/csrf', { credentials: 'include' });
            setState({
                xReqId: r.headers.get('x-req-id'),
                xAuthReq: r.headers.get('x-authdiag-req'),
                xAuthSetCookie: r.headers.get('x-authdiag-setcookie'),
            });
            const w = await fetch('/v1/whoami', { credentials: 'include' });
            setWhoami(await w.json().catch(() => null));
        })();
    }, []);

    if (!state) return null;

    return (
        <div style={{
            position: 'fixed', bottom: 12, right: 12, zIndex: 9999,
            padding: '10px 12px', borderRadius: 12, boxShadow: '0 4px 20px rgba(0,0,0,.2)',
            background: '#0f172a', color: '#e2e8f0', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas',
            fontSize: 12, maxWidth: 420, lineHeight: 1.4
        }}>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>Auth HUD</div>
            <div><b>Req-Id:</b> {state.xReqId || '—'}</div>
            <div><b>Req:</b> {state.xAuthReq || '—'}</div>
            <div style={{ wordBreak: 'break-all' }}><b>Set-Cookie:</b> {state.xAuthSetCookie || '—'}</div>
            <div style={{ marginTop: 6 }}><b>whoami:</b> <code>{JSON.stringify(whoami)}</code></div>
        </div>
    );
}
