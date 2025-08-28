import { apiFetch } from '@/lib/api';

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
