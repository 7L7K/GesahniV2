'use client'

import { useEffect, useState } from 'react'

type Decision = {
    req_id: string
    timestamp?: string
    engine?: string
    model?: string
    route_reason?: string
    latency_ms?: number
    cache_hit?: boolean
    cache_similarity?: number
    self_check?: number
    escalated?: boolean
}

export default function AdminPage() {
    const [items, setItems] = useState<Decision[]>([])
    const [err, setErr] = useState<string>('')

    useEffect(() => {
        const load = async () => {
            try {
                const res = await fetch('/v1/admin/router/decisions')
                if (!res.ok) throw new Error(`HTTP ${res.status}`)
                const body = await res.json()
                setItems(body.items || [])
            } catch (e) {
                setErr(String(e))
            }
        }
        void load()
        const t = setInterval(load, 4000)
        return () => clearInterval(t)
    }, [])

    return (
        <main className="mx-auto max-w-5xl px-4 py-6">
            <h1 className="text-xl font-semibold mb-4">Router Decisions</h1>
            {err && <p className="text-sm text-red-600">{err}</p>}
            <div className="overflow-x-auto rounded border">
                <table className="min-w-full text-sm">
                    <thead className="bg-muted/50">
                        <tr>
                            <th className="px-2 py-1 text-left">Time</th>
                            <th className="px-2 py-1 text-left">Req</th>
                            <th className="px-2 py-1 text-left">Engine</th>
                            <th className="px-2 py-1 text-left">Model</th>
                            <th className="px-2 py-1 text-left">Reason</th>
                            <th className="px-2 py-1 text-right">Latency</th>
                            <th className="px-2 py-1 text-right">Cache</th>
                            <th className="px-2 py-1 text-right">SelfChk</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items.map((d) => (
                            <tr key={d.req_id} className="border-t">
                                <td className="px-2 py-1">{d.timestamp?.replace('T', ' ').slice(0, 19) || '-'}</td>
                                <td className="px-2 py-1 font-mono text-[11px]">{d.req_id.slice(0, 8)}</td>
                                <td className="px-2 py-1">{d.engine || '-'}</td>
                                <td className="px-2 py-1">{d.model || '-'}</td>
                                <td className="px-2 py-1">{d.route_reason || '-'}</td>
                                <td className="px-2 py-1 text-right">{d.latency_ms ?? '-'}</td>
                                <td className="px-2 py-1 text-right">{d.cache_hit ? (d.cache_similarity?.toFixed?.(2) ?? 'hit') : '-'}</td>
                                <td className="px-2 py-1 text-right">{d.self_check ? d.self_check.toFixed(2) : '-'}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </main>
    )
}

"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/src/lib/api";

type ErrItem = { timestamp: string; level: string; component: string; msg: string };

export default function AdminPage() {
    const [errors, setErrors] = useState<ErrItem[]>([]);
    const [review, setReview] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState<string | null>(null);

    useEffect(() => {
        async function load() {
            setLoading(true);
            setErr(null);
            try {
                const [eRes, rRes] = await Promise.all([
                    apiFetch("/v1/admin/errors"),
                    apiFetch("/v1/admin/self_review"),
                ]);
                const eBody = await eRes.json();
                const rBody = await rRes.json();
                setErrors((eBody?.errors || []) as ErrItem[]);
                setReview(rBody || {});
            } catch (e: any) {
                setErr(e?.message || "Failed to load");
            } finally {
                setLoading(false);
            }
        }
        load();
    }, []);

    return (
        <div className="mx-auto max-w-5xl p-6 space-y-8">
            <h1 className="text-2xl font-semibold">Admin Dashboard</h1>
            {loading && <div>Loading…</div>}
            {err && <div className="text-red-600">{err}</div>}

            <section>
                <h2 className="text-xl font-medium mb-2">Last 50 errors</h2>
                <div className="rounded border divide-y bg-white dark:bg-zinc-900">
                    {(errors || []).map((e, idx) => (
                        <div key={idx} className="p-3 text-sm flex gap-3">
                            <span className="text-zinc-500 w-44 shrink-0">{e.timestamp}</span>
                            <span className="uppercase text-zinc-600 w-20 shrink-0">{e.level}</span>
                            <span className="text-zinc-700 dark:text-zinc-200 w-64 shrink-0 truncate">{e.component}</span>
                            <span className="text-zinc-800 dark:text-zinc-100">{e.msg}</span>
                        </div>
                    ))}
                    {!errors?.length && <div className="p-3 text-sm text-zinc-500">No recent errors.</div>}
                </div>
            </section>

            <section>
                <h2 className="text-xl font-medium mb-2">Daily self-review</h2>
                <pre className="text-sm rounded bg-zinc-50 dark:bg-zinc-950 p-3 overflow-auto">
                    {JSON.stringify(review, null, 2)}
                </pre>
            </section>
        </div>
    );
}


