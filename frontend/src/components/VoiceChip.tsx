'use client'

import { useMemo } from 'react'

export default function VoiceChip({ engine, tier, cost, className = '' }: { engine: string; tier?: string; cost?: number; className?: string }) {
    const label = useMemo(() => {
        const t = tier ? ` · ${tier}` : ''
        return `${engine}${t}`
    }, [engine, tier])

    const tooltip = useMemo(() => {
        const c = typeof cost === 'number' ? `~$${cost.toFixed(4)}` : '—'
        return `Engine: ${engine}\nTier: ${tier || '—'}\nCost: ${c}`
    }, [engine, tier, cost])

    const color = engine.startsWith('openai') ? 'bg-indigo-600/15 text-indigo-900 dark:text-indigo-200' : 'bg-emerald-600/15 text-emerald-900 dark:text-emerald-200'

    return (
        <span className={`inline-flex items-center rounded px-2 py-0.5 text-[11px] ${color} ${className}`} title={tooltip}>
            {label}
        </span>
    )
}


