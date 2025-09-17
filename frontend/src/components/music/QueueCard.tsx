"use client";

import React from "react";
import { getQueue, type QueueItem as ApiQueueItem } from "@/lib/api";

type QueueItem = {
    id: string;
    name: string;
    artists: string;
    art_url?: string;
};

export default function QueueCard() {
    const [items, setItems] = React.useState<QueueItem[]>([]);
    const [skipCount, setSkipCount] = React.useState(0);
    const lastLoadedAtRef = React.useRef<number>(0);

    const refresh = async () => {
        const q = await getQueue();
        // Transform ApiQueueItem[] to component QueueItem[]
        const transformedItems: QueueItem[] = (q.up_next || []).map((item: ApiQueueItem) => ({
            id: item.id,
            name: item.track.title,
            artists: item.track.artist,
            art_url: item.track.album ? `/album-art/${item.track.album}.jpg` : undefined
        }));
        setItems(transformedItems);
        if (typeof q.skip_count === 'number') setSkipCount(q.skip_count);
        lastLoadedAtRef.current = Date.now();
    };

    React.useEffect(() => {
        refresh();
    }, []);

    React.useEffect(() => {
        const onQueue = () => {
            const now = Date.now();
            // Ignore echo right after our own refresh completes
            if (now - lastLoadedAtRef.current <= 250) return;
            refresh();
        };
        window.addEventListener('music.queue.updated', onQueue as EventListener);
        return () => { window.removeEventListener('music.queue.updated', onQueue as EventListener); };
    }, []);

    const onSkip = () => {
        setSkipCount((s) => s + 1);
    };

    return (
        <div className="rounded-xl bg-card p-4 shadow">
            <div className="flex items-center justify-between mb-2">
                <div className="text-base font-semibold">Up Next</div>
                <div className="text-xs text-muted-foreground">Skips: {skipCount}</div>
            </div>
            <div className="space-y-2">
                {items.map((t) => (
                    <div key={t.id} className="flex items-center gap-3">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={t.art_url || "/placeholder.png"} alt={t.name} className="w-10 h-10 object-cover rounded" />
                        <div className="min-w-0 flex-1">
                            <div className="text-sm font-medium truncate" title={t.name}>{t.name}</div>
                            <div className="text-xs text-muted-foreground truncate" title={t.artists}>{t.artists}</div>
                        </div>
                        <button className="text-xs text-muted-foreground" onClick={onSkip}>Skip</button>
                    </div>
                ))}
            </div>
        </div>
    );
}
