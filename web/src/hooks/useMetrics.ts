import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/apiFetch";

type Metrics = {
    total: number;
    llama: number;
    gpt: number;
    fallback: number;
    cache_hits: number;
    cache_lookups: number;
    ha_failures: number;
};

export function useMetrics() {
    return useQuery({
        queryKey: ["metrics"],
        queryFn: () => apiFetch<{ metrics: Metrics; cache_hit_rate: number }>("/v1/admin/metrics"),
        refetchInterval: 10_000,
    });
}


