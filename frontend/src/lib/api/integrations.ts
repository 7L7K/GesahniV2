import { apiFetch } from '@/lib/api';
import { getGoogleAuthUrl } from '@/lib/api';
import { parseEnvelope } from '@/lib/parseEnvelope';
import { toast } from '@/lib/toast';

export async function disconnectSpotify(): Promise<void> {
  console.log('🎵 SPOTIFY INTEGRATIONS: Starting disconnect process', {
    endpoint: '/v1/spotify/disconnect',
    method: 'DELETE',
    timestamp: new Date().toISOString()
  });

  const res = await apiFetch("/v1/spotify/disconnect", {
    method: "DELETE",
    auth: true,
    credentials: "include",
  });

  console.log('🎵 SPOTIFY INTEGRATIONS: Disconnect API response', {
    status: res.status,
    statusText: res.statusText,
    ok: res.ok,
    headers: Object.fromEntries(res.headers.entries()),
    timestamp: new Date().toISOString()
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    console.error('🎵 SPOTIFY INTEGRATIONS: Disconnect failed', {
      status: res.status,
      body: body,
      timestamp: new Date().toISOString()
    });
    throw new Error(`Spotify disconnect failed (${res.status}) ${body}`);
  }

  console.log('🎵 SPOTIFY INTEGRATIONS: Disconnect successful', {
    timestamp: new Date().toISOString()
  });
}

export async function getIntegrationsStatus() {
  console.log('🎵 INTEGRATIONS: Getting integrations status', {
    endpoint: '/v1/integrations/status',
    timestamp: new Date().toISOString()
  });

  const res = await apiFetch("/v1/integrations/status", {
    auth: true,
    credentials: "include",
  });

  console.log('🎵 INTEGRATIONS: Status API response', {
    status: res.status,
    statusText: res.statusText,
    ok: res.ok,
    timestamp: new Date().toISOString()
  });

  if (!res.ok) {
    console.error('🎵 INTEGRATIONS: Failed to load integrations status', {
      status: res.status,
      statusText: res.statusText,
      timestamp: new Date().toISOString()
    });
    throw new Error("Failed to load integrations status");
  }

  const data = await res.json();
  console.log('🎵 INTEGRATIONS: Status data received', {
    data: data,
    timestamp: new Date().toISOString()
  });

  return data;
}

// Google integration helpers
export async function getGoogleStatus() {
  console.log('🎵 GOOGLE INTEGRATIONS: Getting Google status', {
    endpoint: '/v1/google/status',
    timestamp: new Date().toISOString()
  });

  const res = await apiFetch('/v1/google/status', { method: 'GET', credentials: 'include', auth: true });

  console.log('🎵 GOOGLE INTEGRATIONS: Status API response', {
    status: res.status,
    statusText: res.statusText,
    ok: res.ok,
    timestamp: new Date().toISOString()
  });

  if (!res.ok) {
    console.error('🎵 GOOGLE INTEGRATIONS: Failed to fetch Google status', {
      status: res.status,
      statusText: res.statusText,
      timestamp: new Date().toISOString()
    });
    throw new Error('Failed to fetch Google status');
  }

  const data = await res.json();
  console.log('🎵 GOOGLE INTEGRATIONS: Status data received', {
    data: data,
    timestamp: new Date().toISOString()
  });

  return data;
}

export async function getGoogleHealth() {
  console.log('🎵 GOOGLE INTEGRATIONS: Getting Google health', {
    endpoint: '/v1/health/google',
    timestamp: new Date().toISOString()
  });

  const res = await apiFetch('/v1/health/google', { method: 'GET', credentials: 'include', auth: true });

  console.log('🎵 GOOGLE INTEGRATIONS: Health API response', {
    status: res.status,
    statusText: res.statusText,
    ok: res.ok,
    timestamp: new Date().toISOString()
  });

  if (!res.ok) {
    console.error('🎵 GOOGLE INTEGRATIONS: Failed to fetch Google health', {
      status: res.status,
      statusText: res.statusText,
      timestamp: new Date().toISOString()
    });
    throw new Error('Failed to fetch Google health');
  }

  const data = await res.json();
  console.log('🎵 GOOGLE INTEGRATIONS: Health data received', {
    data: data,
    timestamp: new Date().toISOString()
  });

  return data;
}

export async function connectGoogle(next: string = '/settings#google=connected'): Promise<{ authorize_url?: string } | null> {
  console.log('🎵 GOOGLE INTEGRATIONS: Starting Google connect', {
    next: next,
    timestamp: new Date().toISOString()
  });

  // Use the canonical login_url endpoint so state format matches callback verification
  const authUrl = await getGoogleAuthUrl(next);

  console.log('🎵 GOOGLE INTEGRATIONS: Google auth URL obtained', {
    hasAuthUrl: !!authUrl,
    authUrlLength: authUrl?.length || 0,
    timestamp: new Date().toISOString()
  });

  return { authorize_url: authUrl };
}

export async function disconnectGoogle(): Promise<void> {
  console.log('🎵 GOOGLE INTEGRATIONS: Starting Google disconnect', {
    endpoint: '/v1/google/disconnect',
    timestamp: new Date().toISOString()
  });

  const res = await apiFetch('/v1/google/disconnect', { method: 'DELETE', credentials: 'include', auth: true });

  console.log('🎵 GOOGLE INTEGRATIONS: Disconnect API response', {
    status: res.status,
    statusText: res.statusText,
    ok: res.ok,
    timestamp: new Date().toISOString()
  });

  if (!res.ok) {
    console.error('🎵 GOOGLE INTEGRATIONS: Failed to disconnect Google', {
      status: res.status,
      statusText: res.statusText,
      timestamp: new Date().toISOString()
    });
    throw new Error('Failed to disconnect Google');
  }

  console.log('🎵 GOOGLE INTEGRATIONS: Google disconnect successful', {
    timestamp: new Date().toISOString()
  });
}

export async function toggleGoogleService(service: string, enable: boolean) {
  const verb = enable ? 'enable' : 'disable';
  const url = `/v1/google/service/${encodeURIComponent(service)}/${verb}`;

  console.log('🎵 GOOGLE INTEGRATIONS: Toggling Google service', {
    service: service,
    enable: enable,
    verb: verb,
    url: url,
    timestamp: new Date().toISOString()
  });

  const res = await apiFetch(url, { method: 'POST', credentials: 'include', auth: true });

  console.log('🎵 GOOGLE INTEGRATIONS: Service toggle API response', {
    service: service,
    verb: verb,
    status: res.status,
    statusText: res.statusText,
    ok: res.ok,
    timestamp: new Date().toISOString()
  });

  if (res.ok) {
    const data = await res.json().catch(() => ({ ok: true }));
    console.log('🎵 GOOGLE INTEGRATIONS: Service toggle successful', {
      service: service,
      verb: verb,
      data: data,
      timestamp: new Date().toISOString()
    });
    return data;
  }

  // Parse envelope for helpful UI hints
  const env = await parseEnvelope(res).catch(() => null);

  console.log('🎵 GOOGLE INTEGRATIONS: Service toggle failed', {
    service: service,
    verb: verb,
    envelope: env,
    timestamp: new Date().toISOString()
  });

  if (env && env.code === 'account_mismatch') {
    console.warn('🎵 GOOGLE INTEGRATIONS: Account mismatch detected', {
      service: service,
      env: env,
      timestamp: new Date().toISOString()
    });
    // Let UI handle modal; also throw structured error
    const err = new Error(env.message || 'account_mismatch');
    (err as any).envelope = env;
    throw err;
  }

  const msg = (env && env.message) || `Failed to ${verb} ${service}`;
  console.error('🎵 GOOGLE INTEGRATIONS: Service toggle error', {
    service: service,
    verb: verb,
    message: msg,
    envelope: env,
    timestamp: new Date().toISOString()
  });

  toast.error(msg);
  throw new Error(msg);
}
