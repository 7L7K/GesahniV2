/**
 * Type definitions for API responses and data structures
 */

export type MusicState = {
  is_playing: boolean;
  progress_ms: number;
  track: {
    id: string;
    title: string;
    artist: string;
    album?: string;
    duration_ms: number;
    explicit: boolean;
    provider: string;
  } | null;
  device: {
    id: string;
    name: string;
    area?: string;
    provider?: string;
    type: string;
    volume_percent: number;
    is_active: boolean;
  } | null;
  queue: Array<{
    id: string;
    track: {
      id: string;
      title: string;
      artist: string;
      album?: string;
      duration_ms: number;
      explicit: boolean;
      provider: string;
    };
    requested_by?: string;
    vibe?: Record<string, unknown>;
  }>;
  shuffle: boolean;
  repeat: 'off' | 'track' | 'context';
  volume_percent: number;
  provider: string;
  server_ts_at_position: number;
};

export type AuthErrorType =
  | 'network_error'
  | 'invalid_credentials'
  | 'account_disabled'
  | 'rate_limited'
  | 'server_error'
  | 'unknown_error';

export type AuthErrorEvent = {
  type: AuthErrorType;
  message: string;
  timestamp: number;
  details?: Record<string, unknown>;
};

export type SessionInfo = { session_id: string; device_id: string; device_name?: string; created_at?: number; last_seen_at?: number; current?: boolean }

export type PatInfo = { id: string; name: string; scopes: string[]; exp_at?: number | null; last_used_at?: number | null }

export type OnboardingStatus = {
  completed: boolean;
  steps: { step: string; completed: boolean; data?: Record<string, unknown> | null }[];
  current_step: number;
};

export type TvConfig = {
  ambient_rotation: number;
  rail: 'safe' | 'admin' | 'open';
  quiet_hours?: { start?: string; end?: string } | null;
  default_vibe: string;
};
