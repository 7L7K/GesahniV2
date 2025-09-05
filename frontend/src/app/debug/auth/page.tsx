'use client';
import { useEffect, useState } from 'react';

export default function AuthDebug() {
    const [r, setR] = useState<any>({});
    useEffect(() => {
        (async () => {
            const me = await fetch('http://localhost:8000/v1/me', { credentials: 'include' })
                .then(r => ({ ok: r.ok, status: r.status, h: Object.fromEntries(r.headers), body: r.json().catch(() => null) }))
                .catch(e => ({ error: String(e) }));
            const diag = await fetch('http://localhost:8000/v1/_diag/auth', { credentials: 'include' })
                .then(r => r.json()).catch(e => ({ error: String(e) }));
            setR({ me, diag });
        })();
    }, []);
    return <pre className="p-6 text-xs overflow-auto">{JSON.stringify(r, null, 2)}</pre>;
}

