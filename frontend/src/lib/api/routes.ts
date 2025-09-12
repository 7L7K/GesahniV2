/**
 * Canonical API route constants
 * Central source of truth for all backend API endpoints
 */

export const API_ROUTES = {
    // Authentication endpoints
    AUTH: {
        LOGIN: '/v1/auth/login',
        REGISTER: '/v1/auth/register',
        LOGOUT: '/v1/auth/logout',
        REFRESH: '/v1/auth/refresh',
        WHOAMI: '/v1/whoami',  // Canonical backend path
        CSRF: '/v1/csrf',
        FINISH: '/v1/auth/finish',
        GOOGLE_LOGIN_URL: '/v1/auth/google/login_url',
    },

    // Status endpoints
    STATUS: {
        ROOT: '/v1/status',
        RATE_LIMIT: '/v1/status/rate_limit',
        OBSERVABILITY: '/v1/status/observability',
        VECTOR_STORE: '/v1/status/vector_store',
        INTEGRATIONS: '/v1/status/integrations',
        FEATURES: '/v1/status/features',
    },

    // Legacy aliases (for backward compatibility during migration)
    LEGACY: {
        LOGIN: '/v1/login',
        REGISTER: '/v1/register',
        LOGOUT: '/v1/logout',
        REFRESH: '/v1/refresh',
        WHOAMI: '/v1/whoami',
        CSRF: '/v1/csrf',
    },

    // Health endpoints
    HEALTH: {
        LIVE: '/health/live',
        READY: '/health/ready',
        STARTUP: '/health/startup',
        HEALTHZ_READY: '/healthz/ready',
        HEALTHZ_DEPS: '/healthz/deps',
    },

    // Other endpoints (keeping existing structure)
    ASK: '/v1/ask',
    STATE: '/v1/state',
    BUDGET: '/v1/budget',
    MUSIC: '/v1/music',
    VIBE: '/v1/vibe',
    QUEUE: '/v1/queue',
    RECOMMENDATIONS: '/v1/recommendations',
    DEVICES: '/v1/music/devices',
    DEVICE: '/v1/music/device',
    SESSIONS: '/v1/sessions',
    PATS: '/v1/pats',
    ONBOARDING_STATUS: '/v1/onboarding/status',
    ONBOARDING_COMPLETE: '/v1/onboarding/complete',
    PROFILE: '/v1/profile',
    TV_CONFIG: '/v1/tv/config',
    MODELS: '/v1/models',
    INTEGRATIONS_STATUS: '/v1/integrations/status',

    // Spotify integration
    SPOTIFY: {
        STATUS: '/v1/spotify/status',
        CONNECT: '/v1/spotify/connect',
    },

    // Google integration
    GOOGLE: {
        HEALTH: '/v1/health/google',
    },

    // Admin endpoints
    ADMIN: {
        METRICS: '/v1/admin/metrics',
        SYSTEM_STATUS: '/v1/admin/system/status',
    },

    // Metrics
    METRICS: '/metrics',
} as const;

// Type-safe route access
export type AuthRoutes = typeof API_ROUTES.AUTH;
export type StatusRoutes = typeof API_ROUTES.STATUS;
export type LegacyRoutes = typeof API_ROUTES.LEGACY;
