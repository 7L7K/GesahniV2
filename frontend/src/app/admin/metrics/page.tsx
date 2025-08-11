"use client";

import { useMemo } from "react";
import { useAdminMetrics } from "@/lib/api";

export default function AdminMetrics() {
  const token = useMemo(() => process.env.NEXT_PUBLIC_ADMIN_TOKEN || '', []);
  const { data, isLoading, error } = useAdminMetrics(token);

  return (
    <div className="mx-auto max-w-5xl p-6 space-y-8">
      <h1 className="text-2xl font-semibold">Admin Metrics</h1>
      {isLoading && <div role="status" aria-live="polite">Loading…</div>}
      {error && <div className="text-red-600" role="alert">{error.message}</div>}
      {data && (
        <>
          <section>
            <h2 className="text-xl font-medium mb-2">Cache Hit Rate</h2>
            <div className="text-4xl font-bold">{data.cache_hit_rate}%</div>
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


