'use client';
import React, { useEffect, useState } from 'react';
import { useAuthState } from '@/hooks/useAuth';
import { apiFetch } from '@/lib/api';
import { getAuthOrchestrator } from '@/services/authOrchestrator';

interface AuthHudState {
    xReqId: string | null;
    xAuthReq: string | null;
    xAuthSetCookie: string | null;
    xAuthOrigin: string | null;
    xAuthUserAgent: string | null;
    xAuthCSRF: string | null;
    xAuthAuthCookies: string | null;
    whoamiData: any;
    csrfData: any;
    cookieConfig: any;
    sessionInfo: any;
    jwtInfo: any;
    refreshInfo: any;
    envInfo: any;
    timing: any;
    errors: any[];
}

export default function AuthHud() {
    const authState = useAuthState();
    const [state, setState] = useState<AuthHudState | null>(null);
    const [expanded, setExpanded] = useState(false);

    // Debug: Track AuthHUD re-renders to verify reactive auth state updates
    console.info('🎨 AUTH_HUD_RENDER:', {
        authed: authState.is_authenticated,
        source: authState.source,
        userId: authState.user_id,
        sessionReady: authState.session_ready,
        timestamp: new Date().toISOString(),
    });

    // Debug: Track when auth state actually changes
    React.useEffect(() => {
        console.info('🔄 AUTH_HUD_STATE_CHANGED:', {
            is_authenticated: authState.is_authenticated,
            session_ready: authState.session_ready,
            source: authState.source,
            user_id: authState.user_id,
            whoamiOk: authState.whoamiOk,
            version: authState.version,
            timestamp: new Date().toISOString(),
        });
    }, [authState.is_authenticated, authState.session_ready, authState.source, authState.user_id, authState.whoamiOk, authState.version]);

    useEffect(() => {
        (async () => {
            // Ensure fetch is available
            if (typeof fetch === 'undefined') {
                console.warn('AuthHUD: fetch not available');
                return;
            }

            const startTime = Date.now();
            const errors: any[] = [];

            try {
                // Get basic diagnostic headers from CSRF endpoint
                const csrfResponse = await apiFetch('/v1/csrf');
                const csrfData = await csrfResponse.json().catch(() => null);

                // Get comprehensive auth state from auth orchestrator
                const authOrchestrator = getAuthOrchestrator();
                const whoamiData = authOrchestrator.getCachedIdentity();

                // Get cookie configuration info
                const cookieConfigResponse = await apiFetch('/v1/auth/cookie-config', {
                    headers: { 'X-Auth-Orchestrator': 'debug-bypass' }
                }).catch(() => null);
                const cookieConfig = cookieConfigResponse ? await cookieConfigResponse.json().catch(() => null) : null;

                // Get session information
                const sessionResponse = await apiFetch('/v1/auth/session-info', {
                    headers: { 'X-Auth-Orchestrator': 'debug-bypass' }
                }).catch(() => null);
                const sessionInfo = sessionResponse ? await sessionResponse.json().catch(() => null) : null;

                // Get JWT token information
                const jwtResponse = await apiFetch('/v1/auth/jwt-info', {
                    headers: { 'X-Auth-Orchestrator': 'debug-bypass' }
                }).catch(() => null);
                const jwtInfo = jwtResponse ? await jwtResponse.json().catch(() => null) : null;

                // Get refresh token information
                const refreshResponse = await apiFetch('/v1/auth/refresh-info', {
                    headers: { 'X-Auth-Orchestrator': 'debug-bypass' }
                }).catch(() => null);
                const refreshInfo = refreshResponse ? await refreshResponse.json().catch(() => null) : null;

                // Get environment information
                const envResponse = await apiFetch('/v1/auth/env-info', {
                    headers: { 'X-Auth-Orchestrator': 'debug-bypass' }
                }).catch(() => null);
                const envInfo = envResponse ? await envResponse.json().catch(() => null) : null;

                const endTime = Date.now();

                setState({
                    xReqId: csrfResponse.headers.get('x-req-id'),
                    xAuthReq: csrfResponse.headers.get('x-authdiag-req'),
                    xAuthSetCookie: csrfResponse.headers.get('x-authdiag-setcookie'),
                    xAuthOrigin: csrfResponse.headers.get('x-authdiag-origin'),
                    xAuthUserAgent: csrfResponse.headers.get('x-authdiag-useragent'),
                    xAuthCSRF: csrfResponse.headers.get('x-authdiag-csrf'),
                    xAuthAuthCookies: csrfResponse.headers.get('x-authdiag-authcookies'),
                    whoamiData,
                    csrfData,
                    cookieConfig,
                    sessionInfo,
                    jwtInfo,
                    refreshInfo,
                    envInfo,
                    timing: {
                        totalMs: endTime - startTime,
                        timestamp: new Date().toISOString()
                    },
                    errors
                });
            } catch (error) {
                errors.push({ type: 'fetch_error', message: error instanceof Error ? error.message : String(error), timestamp: new Date().toISOString() });
                setState({
                    xReqId: null,
                    xAuthReq: null,
                    xAuthSetCookie: null,
                    xAuthOrigin: null,
                    xAuthUserAgent: null,
                    xAuthCSRF: null,
                    xAuthAuthCookies: null,
                    whoamiData: null,
                    csrfData: null,
                    cookieConfig: null,
                    sessionInfo: null,
                    jwtInfo: null,
                    refreshInfo: null,
                    envInfo: null,
                    timing: { totalMs: Date.now() - startTime, timestamp: new Date().toISOString() },
                    errors
                });
            }
        })();
    }, []);

    if (!state) return null;

    const formatValue = (value: any, maxLength = 50) => {
        if (value === null || value === undefined) return '—';
        const str = typeof value === 'object' ? JSON.stringify(value) : String(value);
        return str.length > maxLength ? str.substring(0, maxLength) + '...' : str;
    };

    const getStatusColor = (status: string) => {
        switch (status?.toLowerCase()) {
            case 'ok': case 'success': case 'authenticated': return '#10b981';
            case 'error': case 'failed': case 'invalid': return '#ef4444';
            case 'warning': case 'expired': return '#f59e0b';
            default: return '#6b7280';
        }
    };

    return (
        <div style={{
            position: 'fixed', bottom: 12, right: 12, zIndex: 9999,
            padding: '10px 12px', borderRadius: 12, boxShadow: '0 4px 20px rgba(0,0,0,.2)',
            background: '#0f172a', color: '#e2e8f0', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas',
            fontSize: 11, maxWidth: expanded ? 600 : 420, lineHeight: 1.4, maxHeight: expanded ? '80vh' : 'auto',
            overflow: expanded ? 'auto' : 'visible'
        }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <div style={{ fontWeight: 700 }}>Auth HUD</div>
                <button
                    onClick={() => setExpanded(!expanded)}
                    style={{
                        background: 'none', border: 'none', color: '#e2e8f0', cursor: 'pointer',
                        fontSize: 10, padding: '2px 4px', borderRadius: 4
                    }}
                >
                    {expanded ? '−' : '+'}
                </button>
            </div>

            {/* Basic Info */}
            <div style={{ marginBottom: 4 }}>
                <b>Req-Id:</b> {state.xReqId || '—'}
            </div>
            <div style={{ marginBottom: 4 }}>
                <b>Req:</b> {state.xAuthReq || '—'}
            </div>
            <div style={{ marginBottom: 4, wordBreak: 'break-all' }}>
                <b>Set-Cookie:</b> {state.xAuthSetCookie || '—'}
            </div>

            {/* Additional Diagnostic Headers */}
            {expanded && (
                <>
                    <div style={{ marginBottom: 4 }}>
                        <b>Origin:</b> {state.xAuthOrigin || '—'}
                    </div>
                    <div style={{ marginBottom: 4 }}>
                        <b>User-Agent:</b> {state.xAuthUserAgent || '—'}
                    </div>
                    <div style={{ marginBottom: 4 }}>
                        <b>CSRF:</b> <span style={{ color: getStatusColor(state.xAuthCSRF === 'present' ? 'success' : 'error') }}>
                            {state.xAuthCSRF || '—'}
                        </span>
                    </div>
                    <div style={{ marginBottom: 4 }}>
                        <b>Auth Cookies:</b> {state.xAuthAuthCookies || '—'}
                    </div>
                </>
            )}

            {/* Auth State */}
            <div style={{ marginTop: 6, marginBottom: 4 }}>
                <b>Auth State:</b>
                <div style={{ marginLeft: 8, fontSize: 10 }}>
                    <div>• <span style={{ color: getStatusColor(authState.is_authenticated ? 'authenticated' : 'error') }}>
                        {authState.is_authenticated ? '✓' : '✗'}</span> Authenticated: {String(authState.is_authenticated)}
                    </div>
                    <div>• <span style={{ color: getStatusColor(authState.session_ready ? 'success' : 'error') }}>
                        {authState.session_ready ? '✓' : '✗'}</span> Session Ready: {String(authState.session_ready)}
                    </div>
                    <div>• User ID: {formatValue(authState.user_id)}</div>
                    <div>• Source: <span style={{ color: getStatusColor(authState.source) }}>{authState.source}</span></div>
                    <div>• Last Check: {authState.lastChecked ? new Date(authState.lastChecked).toLocaleTimeString() : '—'}</div>
                    {authState.error && (
                        <div style={{ color: '#ef4444' }}>• Error: {formatValue(authState.error)}</div>
                    )}
                </div>
            </div>

            {/* Expanded Details */}
            {expanded && (
                <>
                    {/* Whoami Data */}
                    {state.whoamiData && (
                        <div style={{ marginTop: 8, marginBottom: 4 }}>
                            <b>Whoami Data:</b>
                            <div style={{ marginLeft: 8, fontSize: 10 }}>
                                <div>• JWT Status: <span style={{ color: getStatusColor(state.whoamiData.jwt_status) }}>
                                    {state.whoamiData.jwt_status || '—'}</span>
                                </div>
                                <div>• Schema Version: {state.whoamiData.schema_version || '—'}</div>
                                <div>• Generated At: {state.whoamiData.generated_at || '—'}</div>
                                {state.whoamiData.auth_source_conflict && (
                                    <div style={{ color: '#f59e0b' }}>• ⚠️ Auth Source Conflict</div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* JWT Info */}
                    {state.jwtInfo && (
                        <div style={{ marginTop: 8, marginBottom: 4 }}>
                            <b>JWT Info:</b>
                            <div style={{ marginLeft: 8, fontSize: 10 }}>
                                <div>• Expires: {state.jwtInfo.expires_at || '—'}</div>
                                <div>• Issued At: {state.jwtInfo.issued_at || '—'}</div>
                                <div>• Time To Live: {state.jwtInfo.ttl_seconds ? `${state.jwtInfo.ttl_seconds}s` : '—'}</div>
                                <div>• Claims: {formatValue(state.jwtInfo.claims, 30)}</div>
                            </div>
                        </div>
                    )}

                    {/* Cookie Config */}
                    {state.cookieConfig && (
                        <div style={{ marginTop: 8, marginBottom: 4 }}>
                            <b>Cookie Config:</b>
                            <div style={{ marginLeft: 8, fontSize: 10 }}>
                                <div>• SameSite: <span style={{ color: getStatusColor(state.cookieConfig.samesite) }}>
                                    {state.cookieConfig.samesite}</span>
                                </div>
                                <div>• Secure: <span style={{ color: getStatusColor(state.cookieConfig.secure ? 'success' : 'warning') }}>
                                    {String(state.cookieConfig.secure)}</span>
                                </div>
                                <div>• Domain: {state.cookieConfig.domain || 'host-only'}</div>
                                <div>• Path: {state.cookieConfig.path || '/'}</div>
                                <div>• HttpOnly: {String(state.cookieConfig.httponly)}</div>
                            </div>
                        </div>
                    )}

                    {/* Session Info */}
                    {state.sessionInfo && (
                        <div style={{ marginTop: 8, marginBottom: 4 }}>
                            <b>Session Info:</b>
                            <div style={{ marginLeft: 8, fontSize: 10 }}>
                                <div>• Session ID: {formatValue(state.sessionInfo.session_id)}</div>
                                <div>• Created: {state.sessionInfo.created_at || '—'}</div>
                                <div>• Last Activity: {state.sessionInfo.last_activity || '—'}</div>
                                <div>• Expires: {state.sessionInfo.expires_at || '—'}</div>
                                <div>• Store Status: <span style={{ color: getStatusColor(state.sessionInfo.store_status) }}>
                                    {state.sessionInfo.store_status || '—'}</span>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Refresh Info */}
                    {state.refreshInfo && (
                        <div style={{ marginTop: 8, marginBottom: 4 }}>
                            <b>Refresh Info:</b>
                            <div style={{ marginLeft: 8, fontSize: 10 }}>
                                <div>• Available: <span style={{ color: getStatusColor(state.refreshInfo.available ? 'success' : 'error') }}>
                                    {String(state.refreshInfo.available)}</span>
                                </div>
                                <div>• Expires: {state.refreshInfo.expires_at || '—'}</div>
                                <div>• Rotation Eligible: <span style={{ color: getStatusColor(state.refreshInfo.rotation_eligible ? 'success' : 'error') }}>
                                    {String(state.refreshInfo.rotation_eligible)}</span>
                                </div>
                                <div>• Family ID: {formatValue(state.refreshInfo.family_id)}</div>
                            </div>
                        </div>
                    )}

                    {/* CSRF Info */}
                    {state.csrfData && (
                        <div style={{ marginTop: 8, marginBottom: 4 }}>
                            <b>CSRF Info:</b>
                            <div style={{ marginLeft: 8, fontSize: 10 }}>
                                <div>• Token: {formatValue(state.csrfData.token)}</div>
                                <div>• Valid: <span style={{ color: getStatusColor(state.csrfData.valid ? 'success' : 'error') }}>
                                    {String(state.csrfData.valid)}</span>
                                </div>
                                <div>• Expires: {state.csrfData.expires_at || '—'}</div>
                            </div>
                        </div>
                    )}

                    {/* Environment Info */}
                    {state.envInfo && (
                        <div style={{ marginTop: 8, marginBottom: 4 }}>
                            <b>Environment:</b>
                            <div style={{ marginLeft: 8, fontSize: 10 }}>
                                <div>• Mode: <span style={{ color: getStatusColor(state.envInfo.mode) }}>
                                    {state.envInfo.mode || '—'}</span>
                                </div>
                                <div>• Dev Mode: {String(state.envInfo.dev_mode)}</div>
                                <div>• CORS Origins: {formatValue(state.envInfo.cors_origins)}</div>
                                <div>• Auth Debug: {String(state.envInfo.auth_debug)}</div>
                            </div>
                        </div>
                    )}

                    {/* Timing */}
                    <div style={{ marginTop: 8, marginBottom: 4 }}>
                        <b>Timing:</b>
                        <div style={{ marginLeft: 8, fontSize: 10 }}>
                            <div>• Total: {state.timing.totalMs}ms</div>
                            <div>• Timestamp: {new Date(state.timing.timestamp).toLocaleTimeString()}</div>
                        </div>
                    </div>

                    {/* Errors */}
                    {state.errors.length > 0 && (
                        <div style={{ marginTop: 8, marginBottom: 4 }}>
                            <b style={{ color: '#ef4444' }}>Errors:</b>
                            <div style={{ marginLeft: 8, fontSize: 10 }}>
                                {state.errors.map((error, i) => (
                                    <div key={i} style={{ color: '#ef4444' }}>
                                        • {error.type}: {error.message}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
