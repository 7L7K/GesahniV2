"use client";

import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";

type BatteryInfo = { level: number; charging: boolean } | null;

function useBattery(): BatteryInfo {
    const [bat, setBat] = useState<BatteryInfo>(null);
    useEffect(() => {
        let mounted = true;
        (async () => {
            try {
                const navAny = navigator as any;
                if (navAny.getBattery) {
                    const b = await navAny.getBattery();
                    const set = () => mounted && setBat({ level: b.level, charging: b.charging });
                    set();
                    b.addEventListener("levelchange", set);
                    b.addEventListener("chargingchange", set);
                    return () => { b.removeEventListener("levelchange", set); b.removeEventListener("chargingchange", set); };
                }
            } catch { }
        })();
        return () => { mounted = false; };
    }, []);
    return bat;
}

function useHeartbeat() {
    const [lastAt, setLastAt] = useState<number>(0);
    // Default to true during SSR; update on mount
    const [online, setOnline] = useState<boolean>(true);
    useEffect(() => {
        const onPing = () => setLastAt(Date.now());
        const onHeart = () => setLastAt(Date.now());
        window.addEventListener('music.state', onPing as any);
        window.addEventListener('device.heartbeat', onHeart as any);
        const on = () => setOnline(true);
        const off = () => setOnline(false);
        window.addEventListener("online", on);
        window.addEventListener("offline", off);
        return () => {
            window.removeEventListener('music.state', onPing as any);
            window.removeEventListener('device.heartbeat', onHeart as any);
            window.removeEventListener("online", on);
            window.removeEventListener("offline", off);
        };
    }, []);
    return { lastAt, online };
}

export function VitalsBadge() {
    const { lastAt, online } = useHeartbeat();
    const bat = useBattery();
    const [mounted, setMounted] = useState<boolean>(false);
    // Avoid Date.now() on server; only compute stale after mount
    const stale = useMemo(() => {
        if (!mounted) return false;
        return (Date.now() - (lastAt || 0)) > 60_000;
    }, [lastAt, mounted]);
    const netLabel = mounted ? (online && !stale ? "Online ✓" : stale ? "Reconnecting…" : "Offline") : "—";
    const batPct = bat ? Math.round((bat.level || 0) * 100) : null;
    const batLabel = batPct !== null ? `${batPct}%${bat?.charging ? " ⚡" : ""}` : "—";

    useEffect(() => { setMounted(true); }, []);

    return (
        <div className="flex items-center gap-4 text-white">
            <div className="bg-white/10 rounded-2xl px-5 py-3 text-[28px] min-w-[220px] text-center">{netLabel}</div>
            <div className="bg-white/10 rounded-2xl px-5 py-3 text-[28px] min-w-[160px] text-center">Battery {batLabel}</div>
        </div>
    );
}
