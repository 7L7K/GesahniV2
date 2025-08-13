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
    const [online, setOnline] = useState<boolean>(typeof navigator !== "undefined" ? navigator.onLine : true);
    useEffect(() => {
        const tick = async () => {
            try {
                const res = await apiFetch("/v1/status/features", { method: "GET" });
                if (res.ok) setLastAt(Date.now());
            } catch { }
        };
        tick();
        const t = setInterval(tick, 60_000);
        const on = () => setOnline(true);
        const off = () => setOnline(false);
        window.addEventListener("online", on);
        window.addEventListener("offline", off);
        return () => { clearInterval(t); window.removeEventListener("online", on); window.removeEventListener("offline", off); };
    }, []);
    return { lastAt, online };
}

export function VitalsBadge() {
    const { lastAt, online } = useHeartbeat();
    const bat = useBattery();
    const stale = useMemo(() => (Date.now() - (lastAt || 0)) > 90_000, [lastAt]);
    const netLabel = online && !stale ? "Online ✓" : stale ? "Reconnecting…" : "Offline";
    const batPct = bat ? Math.round((bat.level || 0) * 100) : null;
    const batLabel = batPct !== null ? `${batPct}%${bat?.charging ? " ⚡" : ""}` : "—";

    return (
        <div className="flex items-center gap-4 text-white">
            <div className="bg-white/10 rounded-2xl px-5 py-3 text-[28px] min-w-[220px] text-center">{netLabel}</div>
            <div className="bg-white/10 rounded-2xl px-5 py-3 text-[28px] min-w-[160px] text-center">Battery {batLabel}</div>
        </div>
    );
}


