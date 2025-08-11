"use client";

import { useState } from "react";
import { useRouterDecisions, apiFetch } from "@/lib/api";

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
    const { data, isLoading, error } = useRouterDecisions(50)
    const items: Decision[] = (data?.items as Decision[]) || []

    return (
        <main className="mx-auto max-w-5xl px-4 py-6 space-y-8">
            <section>
                <h1 className="text-xl font-semibold mb-4">Router Decisions</h1>
                {error && <p className="text-sm text-red-600">{error.message}</p>}
                {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
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
                            {!items.length && !isLoading && (
                                <tr><td className="px-2 py-3 text-sm text-muted-foreground" colSpan={8}>No decisions yet.</td></tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </section>

            <section>
                <h2 className="text-xl font-medium mb-2">Daily self-review</h2>
                <SelfReview />
            </section>
        </main>
    );
}

function SelfReview() {
    const [errors, setErrors] = useState<{ timestamp: string; level: string; component: string; msg: string }[]>([])
    type Review = Record<string, unknown> | null
    const [review, setReview] = useState<Review>(null)
    const [loading, setLoading] = useState(true)
    const [err, setErr] = useState<string | null>(null)

    useEffect(() => {
        async function load() {
            setLoading(true)
            setErr(null)
            try {
                const [eRes, rRes] = await Promise.all([
                    apiFetch('/v1/admin/errors'),
                    apiFetch('/v1/admin/self_review'),
                ])
                const eBody = (await eRes.json()) as unknown
                const rBody = (await rRes.json()) as unknown
                const errs = (eBody && typeof eBody === 'object' && (eBody as { errors?: unknown }).errors)
                setErrors(Array.isArray(errs) ? (errs as { timestamp: string; level: string; component: string; msg: string }[]) : [])
                setReview((rBody && typeof rBody === 'object') ? (rBody as Record<string, unknown>) : {})
            } catch (e: unknown) {
                const msg = e instanceof Error ? e.message : 'Failed to load'
                setErr(msg)
            } finally {
                setLoading(false)
            }
        }
        load()
    }, [])

    return (
        <div className="space-y-6">
            {loading && <div>Loading…</div>}
            {err && <div className="text-red-600">{err}</div>}

            <div>
                <h3 className="text-lg font-medium mb-2">Last 50 errors</h3>
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
            </div>

            <div>
                <h3 className="text-lg font-medium mb-2">Self-review</h3>
                <pre className="text-sm rounded bg-zinc-50 dark:bg-zinc-950 p-3 overflow-auto">
                    {JSON.stringify(review, null, 2)}
                </pre>
            </div>
        </div>
    )
}
