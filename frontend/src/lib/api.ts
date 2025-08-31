/**
 * Main API exports - unified interface for all API functionality
 */

// Re-export everything from the modular API structure
export * from './api/auth';
export * from './api/fetch';
export * from './api/websocket';
export * from './api/hooks';
export * from './api/types';
export * from './api/utils';

// Legacy exports for backward compatibility
export { apiFetch } from './api/fetch';
export { wsUrl } from './api/websocket';
export { buildQueryKey, getToken, setTokens, clearTokens, isAuthed } from './api/auth';
