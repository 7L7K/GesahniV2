import { apiFetch } from '@/lib/api';
import { getGoogleAuthUrl } from '@/lib/api';

export async function disconnectSpotify(): Promise<void> {
  const res = await apiFetch("/v1/spotify/disconnect", {
    method: "DELETE",
    auth: true,
    credentials: "include",
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Spotify disconnect failed (${res.status}) ${body}`);
  }
}

export async function getIntegrationsStatus() {
  const res = await apiFetch("/v1/integrations/status", {
    auth: false,
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to load integrations status");
  return res.json();
}

// Google integration helpers
export async function getGoogleStatus() {
  const res = await apiFetch('/v1/google/status', { method: 'GET', credentials: 'include', auth: true });
  if (!res.ok) throw new Error('Failed to fetch Google status');
  return res.json();
}

export async function connectGoogle(next: string = '/settings#google=connected'): Promise<{ authorize_url?: string } | null> {
  // Use the canonical login_url endpoint so state format matches callback verification
  const authUrl = await getGoogleAuthUrl(next);
  return { authorize_url: authUrl };
}

export async function disconnectGoogle(): Promise<void> {
  const res = await apiFetch('/v1/google/disconnect', { method: 'DELETE', credentials: 'include', auth: true });
  if (!res.ok) throw new Error('Failed to disconnect Google');
}
