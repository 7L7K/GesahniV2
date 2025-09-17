'use client';

import { useEffect, useState } from 'react';
import { useAuthState } from '@/hooks/useAuth';

export default function FooterRibbon() {
    const [lastUser, setLastUser] = useState<string>("");
    const [lastBot, setLastBot] = useState<string>("");
    const [quiet, _setQuiet] = useState<boolean>(false);
    const authState = useAuthState();

    useEffect(() => {
        const onToken = (e: Event) => {
            try {
                const msg = (e as CustomEvent).detail as { role: 'user' | 'assistant', text: string };
                if (msg?.role === 'user') setLastUser(msg.text || '');
                if (msg?.role === 'assistant') setLastBot(msg.text || '');
            } catch { }
        };
        window.addEventListener('conversation:update', onToken as EventListener);

        // DISABLED: Status polling should be controlled by orchestrator
        // Only start status polling if authenticated
        // const checkAuthAndPoll = () => {
        //     if (!authState.is_authenticated) return null;

        //     const i = setInterval(async () => {
        //         try {
        //             const res = await apiFetch('/v1/status', { auth: true });
        //             const data = await res.json();
        //             const active = Boolean(data?.quiet_hours?.active);
        //             setQuiet(active);
        //             if (active) document.body.classList.add('quiet-hours'); else document.body.classList.remove('quiet-hours');
        //         } catch { }
        //     }, 60000);

        //     return i;
        // };

        // const intervalId = checkAuthAndPoll();
        return () => {
            window.removeEventListener('conversation:update', onToken as EventListener);
            // if (intervalId) clearInterval(intervalId);
        };
    }, [authState.is_authenticated]); // Re-run when auth state changes

    const trunc = (s: string) => (s.length > 80 ? s.slice(0, 77) + '…' : s);

    if (!lastUser && !lastBot) return null;
    return (
        <div className={`fixed bottom-0 inset-x-0 z-20 text-white backdrop-blur px-4 py-2 ${quiet ? 'bg-black/70' : 'bg-black/80'}`}>
            <div className="mx-auto max-w-4xl text-sm flex gap-4 items-center">
                <span className="text-gray-300">You:</span>
                <span className="text-gray-100">{trunc(lastUser)}</span>
                <span className="text-gray-400">→</span>
                <span className="text-gray-100">{trunc(lastBot)}</span>
            </div>
        </div>
    );
}
