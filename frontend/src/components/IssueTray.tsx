'use client';

import React, { useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';
import ServiceChip from '@/components/ServiceChip';
import { useSpotifyStatus, useMusicDevices } from '@/hooks/useSpotify';

type LogItem = { timestamp: string; level: string; component: string; msg: string };
type LogsResponse = { logs?: LogItem[]; errors?: LogItem[] };
type Health = { status: string; checks?: Record<string, string> };

export default function IssueTray({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    // Fetch fresh health + logs when opening
    (async () => {
      try {
        const [h, l] = await Promise.all([
          apiFetch('/v1/health', { auth: true, dedupe: false, cache: 'no-store' }),
          apiFetch('/v1/logs?limit=100', { auth: true, dedupe: false, cache: 'no-store' }),
        ]);
        if (h.ok) setHealth(await h.json().catch(() => null));
        if (l.ok) {
          const body = (await l.json().catch(() => ({}))) as LogsResponse;
          setLogs(body.logs || body.errors || []);
        }
      } catch {
        // ignore
      }
    })();
  }, [open]);

  // Focus management for accessibility
  useEffect(() => {
    if (open) {
      setTimeout(() => closeRef.current?.focus(), 0);
    }
  }, [open]);

  if (!open) return null;

  return (
    <div role="dialog" aria-modal="true" aria-label="System issues" className="fixed inset-0 z-[60]">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      {/* Tray panel */}
      <div className="absolute right-0 top-0 h-full w-full max-w-md bg-background border-l shadow-xl flex flex-col" style={{ transition: 'none' }}>
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <h2 className="text-sm font-medium">Issues</h2>
          <button ref={closeRef} onClick={onClose} className="text-sm px-2 py-1 rounded border hover:bg-accent focus:outline-none focus:ring-2 focus:ring-ring">Close</button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {/* Health Section */}
          <section>
            <h3 className="text-xs font-semibold uppercase text-muted-foreground mb-2">Health</h3>
            {health ? (
              <div className="space-y-2">
                <div className="text-sm">Overall: <span className={health.status === 'ok' ? 'text-green-600' : health.status === 'degraded' ? 'text-amber-600' : 'text-red-600'}>{health.status}</span></div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(health.checks || {}).map(([k, v]) => (
                    <ServiceChip key={k} name={k} status={String(v)} />
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">Loading…</div>
            )}
          </section>
          {/* Spotify Section */}
          <SpotifyStatusSection />
          {/* Logs Section */}
          <section>
            <h3 className="text-xs font-semibold uppercase text-muted-foreground mb-2">Recent Errors</h3>
            {logs.length === 0 ? (
              <div className="text-sm text-muted-foreground">No recent errors</div>
            ) : (
              <ul className="space-y-2 text-xs">
                {logs.slice(-100).reverse().map((l, i) => (
                  <li key={`${l.timestamp}-${i}`} className="border rounded p-2">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{l.level}</span>
                      <span className="text-muted-foreground">{l.timestamp}</span>
                    </div>
                    <div className="text-muted-foreground">{l.component}</div>
                    <div className="mt-1">{l.msg}</div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function SpotifyStatusSection() {
  const { connected, reason } = useSpotifyStatus(60000);
  const { hasDevice } = useMusicDevices(60000);
  return (
    <section>
      <h3 className="text-xs font-semibold uppercase text-muted-foreground mb-2">Spotify</h3>
      <div className="flex flex-wrap gap-2">
        <ServiceChip name="connected" status={connected ? 'ok' : 'error'} />
        <ServiceChip name="device" status={hasDevice ? 'ok' : 'error'} />
      </div>
      {!connected && reason && (
        <div className="mt-1 text-xs text-muted-foreground">{String(reason)}</div>
      )}
    </section>
  );
}
