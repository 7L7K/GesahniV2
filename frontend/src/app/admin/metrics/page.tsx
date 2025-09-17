"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAdminMetrics } from "@/lib/api";

export default function AdminMetrics() {
  const [token, setToken] = useState('');
  useEffect(() => {
    const envTok = process.env.NEXT_PUBLIC_ADMIN_TOKEN || '';
    const lsTok = typeof window !== 'undefined' ? (localStorage.getItem('admin:token') || '') : '';
    setToken(envTok || lsTok);
  }, []);
  const { data, isLoading, error } = useAdminMetrics(token);

  return (
    <div className="mx-auto max-w-5xl p-6 space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Admin Metrics</h1>
        <Link
          href="/admin/metrics/music"
          className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 text-sm"
        >
          🎵 Music Dashboard
        </Link>
      </div>
      <div className="flex items-center gap-2">
        <input value={token} onChange={(e) => setToken(e.target.value)} onBlur={() => { try { localStorage.setItem('admin:token', token || '') } catch { } }} className="border rounded px-2 py-1 text-sm min-w-48" placeholder="admin token" />
        <button className="border rounded px-2 py-1 text-xs" onClick={() => { try { localStorage.setItem('admin:token', token || '') } catch { } }}>Save</button>
      </div>
      {isLoading && <div role="status" aria-live="polite">Loading…</div>}
      {error && <div className="text-red-600" role="alert">{error.message}</div>}
      {data && (
        <>
          <section>
            <h2 className="text-xl font-medium mb-2">Cache Hit Rate</h2>
            <div className="text-4xl font-bold">{data.cache_hit_rate}%</div>
          </section>
          <section className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="rounded border p-3">
              <div className="text-sm text-muted-foreground">Latency p95</div>
              <div className="text-2xl font-semibold">{data.metrics?.latency_p95_ms ?? 0} ms</div>
            </div>
            <div className="rounded border p-3">
              <div className="text-sm text-muted-foreground">Transcribe Error Rate</div>
              <div className="text-2xl font-semibold">{data.metrics?.transcribe_error_rate ?? 0}%</div>
            </div>
          </section>
          <section>
            <h2 className="text-xl font-medium mb-2">Top Skills</h2>
            <ul className="list-disc pl-6">
              {(data.top_skills || []).map(([name, count]) => (
                <li key={name} className="text-sm">
                  <span className="font-mono">{name}</span> — {count}
                </li>
              ))}
              {!data.top_skills?.length && <li className="text-sm text-zinc-500">No skill usage yet.</li>}
            </ul>
          </section>
          <section>
            <h2 className="text-xl font-medium mb-2">Raw Counters</h2>
            <pre className="text-sm rounded bg-zinc-50 dark:bg-zinc-950 p-3 overflow-auto">{JSON.stringify(data.metrics, null, 2)}</pre>
          </section>
        </>
      )}
    </div>
  );
}
