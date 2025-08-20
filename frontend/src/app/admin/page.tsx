"use client";

import { useMemo, useState, useEffect } from "react";
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
    const [token, setToken] = useState<string>("")
    // Initialize from public env or localStorage
    useEffect(() => {
        const envTok = process.env.NEXT_PUBLIC_ADMIN_TOKEN || ''
        const lsTok = typeof window !== 'undefined' ? (localStorage.getItem('admin:token') || '') : ''
        setToken(envTok || lsTok)
    }, [])
    const [filters, setFilters] = useState<{ engine?: string; model?: string; cache_hit?: string; escalated?: string; q?: string }>({})
    const [cursor, setCursor] = useState<number | null>(0)
    const { data, isLoading, error } = useRouterDecisions(token, 20, { ...filters, cursor: cursor ?? 0 })
    const items: Decision[] = Array.isArray((data as any)?.items) ? ((data as any).items as Decision[]) : []
    useEffect(() => {
        // Debug logging to validate shape during Clerk callback troubleshooting
        // eslint-disable-next-line no-console
        console.log("admin.items", items)
    }, [items])

    return (
        <main className="mx-auto max-w-5xl px-4 py-6 space-y-8">
            <section>
                <div className="flex items-center justify-between mb-4">
                    <h1 className="text-xl font-semibold">Router Decisions</h1>
                    <a className="text-blue-600 underline text-sm" href="/admin/ingest">Memory Ingest</a>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4 text-sm">
                    {/* Vector tile disabled pending stable endpoint */}
                    {/* <TileVector token={token} /> */}
                    <TileCache token={token} />
                    <TileBudget />
                    <TileHA />
                </div>
                {error && <p className="text-sm text-red-600">{error.message}</p>}
                {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
                <div className="flex flex-wrap gap-2 mb-3 items-end">
                    <div className="flex items-center gap-2 mr-4">
                        <label className="text-xs text-muted-foreground">Admin token</label>
                        <input
                            value={token}
                            onChange={(e) => setToken(e.target.value)}
                            onBlur={() => { try { localStorage.setItem('admin:token', token || '') } catch { } }}
                            className="border rounded px-2 py-1 text-sm min-w-48"
                            placeholder="paste token"
                        />
                        <button className="border rounded px-2 py-1 text-xs" onClick={() => { try { localStorage.setItem('admin:token', token || '') } catch { } }}>Save</button>
                    </div>
                    <select className="border rounded px-2 py-1 text-sm" value={filters.engine || ''} onChange={(e) => { setCursor(0); setFilters({ ...filters, engine: e.target.value || undefined }) }}>
                        <option value="">Engine: Any</option>
                        <option value="gpt">gpt</option>
                        <option value="llama">llama</option>
                    </select>
                    <input className="border rounded px-2 py-1 text-sm" placeholder="Model contains" value={filters.model || ''} onChange={(e) => { setCursor(0); setFilters({ ...filters, model: e.target.value || undefined }) }} />
                    <select className="border rounded px-2 py-1 text-sm" value={filters.cache_hit || ''} onChange={(e) => { setCursor(0); setFilters({ ...filters, cache_hit: e.target.value || undefined }) }}>
                        <option value="">Cache: Any</option>
                        <option value="true">Cache: hit</option>
                        <option value="false">Cache: miss</option>
                    </select>
                    <select className="border rounded px-2 py-1 text-sm" value={filters.escalated || ''} onChange={(e) => { setCursor(0); setFilters({ ...filters, escalated: e.target.value || undefined }) }}>
                        <option value="">Escalated: Any</option>
                        <option value="true">Escalated</option>
                        <option value="false">Not escalated</option>
                    </select>
                    <input className="border rounded px-2 py-1 text-sm" placeholder="Reason contains" value={filters.q || ''} onChange={(e) => { setCursor(0); setFilters({ ...filters, q: e.target.value || undefined }) }} />
                    <button className="ml-auto border rounded px-3 py-1 text-sm" onClick={() => { setFilters({}); setCursor(0) }}>Clear</button>
                </div>
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
                <div className="flex items-center gap-2 mt-2">
                    <button disabled={!data?.next_cursor} className="border rounded px-2 py-1 text-sm disabled:opacity-50" onClick={() => setCursor(data?.next_cursor ?? null)}>Next</button>
                    <button disabled={!cursor} className="border rounded px-2 py-1 text-sm disabled:opacity-50" onClick={() => setCursor(0)}>First</button>
                    <div className="text-xs text-muted-foreground ml-auto">{items.length} / {data?.total ?? 0}</div>
                </div>
            </section>

            <section>
                <h2 className="text-xl font-medium mb-2">Daily self-review</h2>
                <SelfReview />
            </section>
        </main>
    );
}

// function TileVector({ token }: { token: string }) {
//     const [data, setData] = useState<{ backend: string; avg_latency_ms?: number; sample_size?: number } | null>(null)
//     useEffect(() => { apiFetch('/v1/status/vector_store').then(r => r.json()).then(setData).catch(() => setData(null)) }, [token])
//     return <div className="rounded border p-3 bg-white/50 dark:bg-zinc-900/50"><div className="text-xs text-muted-foreground">Vector</div><div className="font-medium">{data?.backend || 'unknown'}</div><div className="text-xs">avg {data?.avg_latency_ms ?? 0} ms ({data?.sample_size ?? 0})</div></div>
// }

function TileCache({ token }: { token: string }) {
    const [rate, setRate] = useState<number>(0)
    useEffect(() => {
        const headers: HeadersInit | undefined = undefined
        apiFetch(`/v1/admin/metrics`, { headers }).then(r => r.json()).then(b => setRate(Number(b?.cache_hit_rate || 0))).catch(() => setRate(0))
    }, [token])
    return <div className="rounded border p-3 bg-white/50 dark:bg-zinc-900/50"><div className="text-xs text-muted-foreground">Cache hit-rate</div><div className="font-medium">{rate.toFixed(2)}%</div></div>
}

function TileBudget() {
    const [spent, setSpent] = useState<number>(0)
    const [cap, setCap] = useState<number>(0)
    useEffect(() => { apiFetch('/v1/budget').then(r => r.json()).then(b => { const t = b?.tts; setSpent(Number(t?.spent_usd || 0)); setCap(Number(t?.cap_usd || 0)); }).catch(() => { setSpent(0); setCap(0); }) }, [])
    return <div className="rounded border p-3 bg-white/50 dark:bg-zinc-900/50"><div className="text-xs text-muted-foreground">TTS spend today</div><div className="font-medium">${spent.toFixed(2)} / ${cap.toFixed(2)}</div></div>
}

function TileHA() {
    const [ok, setOk] = useState<boolean | null>(null)
    useEffect(() => { apiFetch('/v1/ha_status').then(r => r.json()).then(() => setOk(true)).catch(() => setOk(false)) }, [])
    return <div className="rounded border p-3 bg-white/50 dark:bg-zinc-900/50"><div className="text-xs text-muted-foreground">Home Assistant</div><div className="font-medium">{ok === null ? '—' : ok ? 'healthy' : 'error'}</div></div>
}

function SelfReview() {
    const [errors, setErrors] = useState<{ timestamp: string; level: string; component: string; msg: string }[]>([])
    type Review = Record<string, unknown> | null
    const [review, setReview] = useState<Review>(null)
    const [loading, setLoading] = useState(true)
    const [err, setErr] = useState<string | null>(null)
    const token = useMemo(() => process.env.NEXT_PUBLIC_ADMIN_TOKEN || '', [])

    useEffect(() => {
        async function load() {
            setLoading(true)
            setErr(null)
            try {
                const headers: HeadersInit | undefined = undefined
                const [eRes, rRes] = await Promise.all([
                    apiFetch(`/v1/admin/errors`, { headers }),
                    apiFetch(`/v1/admin/self_review`, { headers }),
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
