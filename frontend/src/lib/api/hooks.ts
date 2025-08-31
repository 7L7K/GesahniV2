/**
 * React Query hooks for API data fetching
 */

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from './fetch';
import { buildQueryKey } from './auth';

export function useModels() {
  return useQuery({
    queryKey: buildQueryKey("models"),
    queryFn: getModels,
    staleTime: 5 * 60_000,
  });
}

export function useAdminMetrics(token: string) {
  return useQuery<{ metrics: Record<string, number>; cache_hit_rate: number; top_skills: [string, number][] }, Error>({
    queryKey: ["admin_metrics", token],
    queryFn: async () => {
      const headers: HeadersInit = {};
      const res = await apiFetch(`/v1/admin/metrics`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    refetchInterval: 10_000,
  });
}

export function useRouterDecisions(
  token: string,
  limit = 50,
  params: Record<string, unknown> = {},
  opts?: { refetchMs?: number | false; enabled?: boolean }
) {
  return useQuery<{ items: any[]; total: number; next_cursor: number | null }, Error>({
    queryKey: ["router_decisions", token, limit, params],
    queryFn: async () => {
      const usp = new URLSearchParams({ limit: String(limit) });
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null && v !== "") usp.set(k, String(v));
      }
      const headers: HeadersInit = {};
      const res = await apiFetch(`/v1/admin/router/decisions?${usp.toString()}`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    refetchInterval: opts?.refetchMs === false ? false : (opts?.refetchMs ?? 4_000),
    enabled: opts?.enabled !== false,
  });
}

export function useAdminErrors(token: string) {
  return useQuery<{ errors: { timestamp: string; level: string; component: string; msg: string }[] }, Error>({
    queryKey: ["admin_errors", token],
    queryFn: async () => {
      const headers: HeadersInit = {};
      const res = await apiFetch(`/v1/admin/errors`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    refetchInterval: 15_000,
  });
}

export function useSelfReview(token: string) {
  return useQuery<Record<string, unknown> | { status: string }, Error>({
    queryKey: ["self_review", token],
    queryFn: async () => {
      const headers: HeadersInit = {};
      const res = await apiFetch(`/v1/admin/self_review`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    refetchInterval: 60_000,
  });
}

export type UserProfile = {
  name?: string;
  email?: string;
  timezone?: string;
  language?: string;
  communication_style?: string;
  interests?: string[];
  occupation?: string;
  home_location?: string;
  preferred_model?: string;
  notification_preferences?: Record<string, unknown>;
  calendar_integration?: boolean;
  gmail_integration?: boolean;
  onboarding_completed?: boolean;
  // Stage 1 device prefs
  speech_rate?: number;
  input_mode?: "voice" | "touch" | "both";
  font_scale?: number;
  wake_word_enabled?: boolean;
};

export function useProfile() {
  return useQuery<UserProfile, Error>({
    queryKey: buildQueryKey("profile"),
    queryFn: async () => {
      const res = await apiFetch("/v1/profile", { method: "GET" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    staleTime: 60_000,
  });
}

// Import required functions
import { getModels } from '../integrations';
