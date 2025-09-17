"use client";

import React from "react";
import { getRecommendations, type Recommendation } from "@/lib/api";
import { Button } from "@/components/ui/button";

type DiscoveryItem = {
    id: string;
    name: string;
    artists: string;
    art_url?: string;
};

export default function DiscoveryCard() {
    const [items, setItems] = React.useState<DiscoveryItem[]>([]);
    const [loading, setLoading] = React.useState(false);
    const prefersReduced = typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const refresh = async () => {
        setLoading(true);
        try {
            const r = await getRecommendations();
            // Transform Recommendation[] to DiscoveryItem[]
            const transformedItems: DiscoveryItem[] = (r.recommendations || []).map((rec: Recommendation) => ({
                id: rec.id,
                name: rec.title,
                artists: rec.artist,
                art_url: rec.album ? `/album-art/${rec.album}.jpg` : undefined // You may need to adjust this based on your album art handling
            }));
            setItems(transformedItems);
        } finally {
            setLoading(false);
        }
    };

    React.useEffect(() => {
        refresh();
        const onState = () => refresh();
        window.addEventListener('music.state', onState as EventListener);
        return () => { window.removeEventListener('music.state', onState as EventListener); };
    }, []);

    return (
        <div className="rounded-xl bg-card p-4 shadow">
            <div className="flex items-center justify-between mb-2">
                <div className="text-base font-semibold">Discover</div>
                <Button size="sm" variant="ghost" onClick={refresh} disabled={loading}>Refresh</Button>
            </div>
            <div className={`grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 ${prefersReduced ? '' : 'transition-all'}`}>
                {items.slice(0, 5).map((t) => (
                    <div key={t.id} className="rounded-md overflow-hidden bg-muted">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={t.art_url || "/placeholder.png"} alt={t.name} className="w-full h-32 object-cover" />
                        <div className="p-2">
                            <div className="text-sm font-medium truncate" title={t.name}>{t.name}</div>
                            <div className="text-xs text-muted-foreground truncate" title={t.artists}>{t.artists}</div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
