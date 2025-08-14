"use client";

import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            staleTime: 30_000,
            retry: (failureCount: number, error: unknown) => {
                const status = (error as { status?: number; response?: { status?: number } } | undefined)?.status ??
                    (error as { response?: { status?: number } } | undefined)?.response?.status;
                // Never retry common client errors
                if (status === 401 || status === 403 || status === 404 || status === 422) return false;
                // 429 should be handled by api layer via Retry-After; don't multiply here
                if (status === 429) return false;
                // Only allow limited retries for unknown or 5xx-ish errors
                return failureCount < 1;
            },
            refetchOnWindowFocus: false,
        },
    },
});


