/**
 * Whoami Cache Utility
 * Manages client-side caching of whoami responses
 */

import type { WhoamiResponse } from './whoamiResilience';

let cache: { value?: WhoamiResponse; ts?: number } = {};

export const whoamiCache = {
    get(maxAgeMs: number) {
        if (!cache.ts) return undefined;
        if (Date.now() - cache.ts > maxAgeMs) return undefined;
        return cache.value;
    },
    set(v: WhoamiResponse) {
        cache = { value: v, ts: Date.now() };
    },
    clear() {
        cache = {};
    },
};
