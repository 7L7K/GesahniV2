"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

type MetricResp = { metrics: Record<string, number>; cache_hit_rate: number; top_skills: [string, number][] };

export default function AdminMetrics() {
    const [data, setData] = useState<MetricResp | null>(null);
    const [err, setErr] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function load() {
            setLoading(true);
            setErr(null);
            try {
                const res = await apiFetch('/v1/status/admin/metrics');
                if (!res.ok) throw new Error('metrics_failed');
                const body = await res.json();
                setData(body as MetricResp);
            } catch (e: any) {
                setErr(e?.message || 'Failed to load metrics');
            } finally {
                setLoading(false);
            }
        }
        load();
    }, []);

    return (
        <div className="mx-auto max-w-5xl p-6 space-y-8">
            <h1 className="text-2xl font-semibold">Admin Metrics</h1>
            {loading && <div>Loading…</div>}
            {err && <div className="text-red-600">{err}</div>}
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


