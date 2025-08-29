'use client';

import React from 'react';
import { useWsOpen } from '@/hooks/useWs';
import { useHealthPolling } from '@/hooks/useHealth';
import { useSpotifyStatus } from '@/hooks/useSpotify';

function Dot({ ok, label, reason }: { ok: boolean; label: string; reason?: string }) {
  const title = `${label}: ${ok ? 'online' : 'offline'}${reason ? ` — ${reason}` : ''}`;
  return (
    <div className="flex items-center gap-1" title={title} aria-label={title}>
      <span className={`w-2 h-2 rounded-full ${ok ? 'bg-emerald-500' : 'bg-gray-400'}`} />
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}

export default function WsIndicator() {
  const musicOpen = useWsOpen('music', 2000);
  const careOpen = useWsOpen('care', 2000);
  const { health } = useHealthPolling(30000);
  const llamaOk = (health?.checks?.['llama'] || 'ok') === 'ok';
  const spotifyOk = (health?.checks?.['spotify'] || 'ok') === 'ok' || (health?.checks?.['spotify'] || '') === 'skipped';
  const { connected: spotifyConnected } = useSpotifyStatus(45000);
  const musicOk = musicOpen && spotifyOk && spotifyConnected;
  const musicReason = musicOk ? undefined : (!spotifyConnected ? 'not connected' : (!spotifyOk ? 'provider down' : (!musicOpen ? 'socket closed' : 'unknown')));
  return (
    <div className="flex items-center gap-4">
      <Dot ok={musicOk} label="Music" reason={musicReason} />
      <Dot ok={careOpen} label="Care" reason={careOpen ? undefined : 'socket closed'} />
      <Dot ok={llamaOk} label="Model" reason={llamaOk ? undefined : 'llama degraded'} />
    </div>
  );
}
