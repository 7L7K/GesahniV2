'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useHealthPolling } from '@/hooks/useHealth';
import IssueTray from '@/components/IssueTray';

export default function StatusBanner() {
  const { health, hasChecked } = useHealthPolling(15000);
  const [trayOpen, setTrayOpen] = useState(false);
  const [dismissedKey, setDismissedKey] = useState<string | null>(null);

  // Compute a key so we can reset dismissal when status changes
  const statusKey = (() => {
    const s = health?.status || 'ok';
    const failing = Object.entries(health?.checks || {})
      .filter(([k, v]) => k !== 'backend' && (v === 'error' || v === 'degraded'))
      .map(([k]) => k)
      .sort()
      .join(',');
    return `${s}|${failing}`;
  })();

  useEffect(() => {
    try {
      const saved = sessionStorage.getItem('statusBanner:dismissed');
      if (saved) setDismissedKey(saved);
    } catch { /* noop */ }
  }, []);

  useEffect(() => {
    // Reset dismissal when status changes
    if (dismissedKey && dismissedKey !== statusKey) setDismissedKey(null);
  }, [statusKey]);

  const onDismiss = () => {
    try { sessionStorage.setItem('statusBanner:dismissed', statusKey); } catch { /* noop */ }
    setDismissedKey(statusKey);
  };

  if (!hasChecked || !health) return null;
  if (health.status === 'ok') return null;
  if (dismissedKey === statusKey) return null;

  // Offline banner
  const failingCount = (() => {
    const items = Object.entries(health.checks || {})
      .filter(([k, v]) => k !== 'backend' && (v === 'error' || v === 'degraded'));
    return Math.max(1, items.length || (health.status === 'fail' ? 1 : 0));
  })();

  if (health.status === 'fail') {
    return (
      <div className="sticky top-14 z-40 mx-auto max-w-3xl px-4 py-1 text-[12px] bg-red-100 text-red-900 dark:bg-red-900/30 dark:text-red-100" role="status" aria-live="polite">
        <div className="flex items-center justify-between gap-2">
          <span>Backend offline — retrying…</span>
          <div className="flex items-center gap-2">
            <button
            type="button"
            aria-label="Open issue tray"
            className="inline-flex items-center justify-center rounded bg-red-600 text-white text-[11px] px-2 py-0.5 focus:outline-none focus:ring-2 focus:ring-red-700"
            onClick={() => setTrayOpen(true)}
          >
            {failingCount} {failingCount === 1 ? 'Issue' : 'Issues'}
          </button>
            <button
              type="button"
              aria-label="Dismiss status banner"
              className="ml-1 text-xs text-red-900/80 underline underline-offset-2 focus:outline-none focus:ring-2 focus:ring-red-700"
              onClick={onDismiss}
            >
              Dismiss
            </button>
          </div>
          </div>
          <IssueTray open={trayOpen} onClose={() => setTrayOpen(false)} />
        </div>
      );
  }

  // Degraded banner
  if (health.status === 'degraded') {
    const failing = Object.entries(health.checks || {})
      .filter(([k, v]) => k !== 'backend' && (v === 'error' || v === 'degraded'))
      .map(([k]) => k);
    if (failing.length === 0) return null;
    const tooltip = `${failing.join(', ')} down`;
    return (
      <div className="sticky top-14 z-40 mx-auto max-w-3xl px-4 py-1 text-[12px] bg-amber-100 text-amber-900 dark:bg-amber-900/30 dark:text-amber-100" role="status" aria-live="polite">
        <div className="flex items-center justify-between gap-2">
          <span title={tooltip}>⚠︎ Some services degraded: {failing.join(', ')}</span>
          <div className="flex items-center gap-2">
            <button
            type="button"
            aria-label="Open issue tray"
            className="inline-flex items-center justify-center rounded bg-amber-600 text-white text-[11px] px-2 py-0.5 focus:outline-none focus:ring-2 focus:ring-amber-700"
            onClick={() => setTrayOpen(true)}
          >
            {failingCount} {failingCount === 1 ? 'Issue' : 'Issues'}
          </button>
            <button
              type="button"
              aria-label="Dismiss status banner"
              className="ml-1 text-xs text-amber-900/80 underline underline-offset-2 focus:outline-none focus:ring-2 focus:ring-amber-700"
              onClick={onDismiss}
            >
              Dismiss
            </button>
          </div>
        </div>
        <IssueTray open={trayOpen} onClose={() => setTrayOpen(false)} />
      </div>
    );
  }

  return null;
}
