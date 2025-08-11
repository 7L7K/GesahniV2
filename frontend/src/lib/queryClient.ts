"use client";

import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            staleTime: 30_000,
      retry: (failureCount: number, error: unknown) => {
        const status = (error as { status?: number; response?: { status?: number } } | undefined)?.status ??
          (error as { response?: { status?: number } } | undefined)?.response?.status;
                if (status === 401 || status === 403) return false;
                return failureCount < 2;
            },
            refetchOnWindowFocus: false,
        },
    },
});


