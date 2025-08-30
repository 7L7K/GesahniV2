import { apiFetch } from '@/lib/api';
import { getGoogleAuthUrl } from '@/lib/api';
import { parseEnvelope } from '@/lib/parseEnvelope';
import { toast } from '@/lib/toast';

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
    auth: true,
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

export async function getGoogleHealth() {
  const res = await apiFetch('/v1/health/google', { method: 'GET', credentials: 'include', auth: true });
  if (!res.ok) throw new Error('Failed to fetch Google health');
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

export async function toggleGoogleService(service: string, enable: boolean) {
  const verb = enable ? 'enable' : 'disable';
  const url = `/v1/google/service/${encodeURIComponent(service)}/${verb}`;
  const res = await apiFetch(url, { method: 'POST', credentials: 'include', auth: true });
  if (res.ok) return await res.json().catch(() => ({ ok: true }));
  // Parse envelope for helpful UI hints
  const env = await parseEnvelope(res).catch(() => null);
  if (env && env.code === 'account_mismatch') {
    // Let UI handle modal; also throw structured error
    const err = new Error(env.message || 'account_mismatch');
    (err as any).envelope = env;
    throw err;
  }
  const msg = (env && env.message) || `Failed to ${verb} ${service}`;
  toast.error(msg);
  throw new Error(msg);
}
