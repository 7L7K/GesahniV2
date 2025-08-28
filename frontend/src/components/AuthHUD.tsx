"use client";

import { useEffect, useState } from 'react';
import { useAuthState } from '@/hooks/useAuth';

export default function AuthHUD() {
    // Dev-only
    if (process.env.NODE_ENV !== 'development') return null;

    const auth = useAuthState();
    const [mounted, setMounted] = useState(false);
    useEffect(() => { setMounted(true); }, []);
    if (!mounted) return null;

    return (
        <div
            style={{
                position: 'fixed',
                top: '10px',
                right: '10px',
                background: 'rgba(0, 0, 0, 0.8)',
                color: 'white',
                padding: '10px',
                borderRadius: '5px',
                fontSize: '12px',
                fontFamily: 'monospace',
                zIndex: 9999,
                maxWidth: '320px',
                boxShadow: '0 0 10px rgba(0,0,0,0.5)'
            }}
        >
            <div style={{ marginBottom: '8px', fontWeight: 'bold', color: '#00ff00' }}>
                🔐 AUTH HUD (DEV)
            </div>
            <div style={{ lineHeight: '1.4' }}>
                <div>Status: {auth.is_authenticated ? '✅' : '❌'} Auth</div>
                <div>Session: {auth.session_ready ? '✅' : '❌'} Ready</div>
                <div>User ID: {auth.user_id || 'none'}</div>
                <div>Email: {auth.user?.email || 'none'}</div>
                <div>Source: {auth.source}</div>
                <div>Loading: {auth.isLoading ? '🔄' : '✅'}</div>
                {auth.error && (
                    <div style={{ color: '#ff4444', marginTop: '4px' }}>Error: {auth.error}</div>
                )}
            </div>
        </div>
    );
}
