// TypeScript types inferred from GesahniV2 identity API responses
// Generated from app/api/me.py and app/router/auth_api.py

// /v1/whoami response type
export interface WhoAmIResponse {
    user_id: string;
    authenticated: boolean;
    source: 'cookie' | 'bearer' | 'session';
}

// /v1/me response type
export interface MeResponse {
    is_authenticated: boolean;
    session_ready: boolean;
    user_id: string | null;
    user: MeUser | null;
    source: string;
    version: number;
    profile: MeProfile;
    flags: MeFlags;
}

export interface MeUser {
    id: string | null;
    email: string | null;
}

export interface MeProfile {
    user_id: string;
    login_count: number;
    last_login: string | null;
    request_count: number;
}

export interface MeFlags {
    retrieval_pipeline: boolean;
    use_hosted_rerank: boolean;
    debug_model_routing: boolean;
    ablation_flags: string[];
    trace_sample_rate: number;
}

// Union type for error responses
export type IdentityErrorResponse = {
    detail: string;
    status_code?: number;
} | {
    error: string;
    req_id?: string;
    timestamp?: string;
};

// Union type for all possible responses
export type WhoAmIResult = WhoAmIResponse | IdentityErrorResponse;
export type MeResult = MeResponse | IdentityErrorResponse;

// HTTP status code mappings
export const IDENTITY_STATUS_CODES = {
    SUCCESS: 200,
    UNAUTHORIZED: 401,
    FORBIDDEN: 403,
    RATE_LIMITED: 429,
    SERVER_ERROR: 500,
} as const;

// Type guards
export function isWhoAmISuccess(response: WhoAmIResult): response is WhoAmIResponse {
    return 'authenticated' in response && typeof response.authenticated === 'boolean';
}

export function isMeSuccess(response: MeResult): response is MeResponse {
    return 'is_authenticated' in response && typeof response.is_authenticated === 'boolean';
}

export function isIdentityError(response: WhoAmIResult | MeResult): response is IdentityErrorResponse {
    return 'detail' in response || 'error' in response;
}

// Authentication source types
export type AuthSource = 'cookie' | 'bearer' | 'session' | 'missing';

// CSRF token type for protected requests
export interface CSRFToken {
    token: string;
    header: 'X-CSRF-Token';
}

// Request headers for authenticated requests
export interface AuthHeaders {
    'Authorization'?: `Bearer ${string}`;
    'X-CSRF-Token'?: string;
    'Content-Type'?: string;
}

// Cookie names used by the identity system
export const IDENTITY_COOKIES = {
    ACCESS_TOKEN: 'gsn_access',
    SESSION: '__session',
    CSRF_TOKEN: 'csrf_token',
} as const;
