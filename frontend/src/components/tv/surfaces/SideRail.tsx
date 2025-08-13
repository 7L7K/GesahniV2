"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { VitalsBadge } from "@/components/tv/widgets/VitalsBadge";
import { CalendarCard } from "@/components/tv/widgets/CalendarCard";

type WeatherPayload = { now?: { temp?: number | null } };
type CalendarNext = { items: { time: string; title: string }[] };

export function SideRail() {
  const [temp, setTemp] = useState<string>("—");
  const [next, setNext] = useState<string>("");
  useEffect(() => {
    (async () => {
      try {
        const w = await apiFetch("/v1/tv/weather", { method: "GET" }).then(r => r.json()) as WeatherPayload;
        const t = w?.now?.temp;
        if (typeof t === 'number') setTemp(`${Math.round(t)}°F`);
      } catch { }
      try {
        const c = await apiFetch("/v1/tv/calendar/next", { method: "GET" }).then(r => r.json()) as CalendarNext;
        const first = (c.items || [])[0];
        if (first) setNext(`${first.time} ${first.title}`);
      } catch { }
    })();
  }, []);

  return (
    <div className="absolute top-8 right-8 flex flex-col gap-4 w-[360px] text-white">
      <VitalsBadge />
      <div className="bg-white/10 rounded-2xl px-6 py-4 text-[28px] whitespace-nowrap overflow-hidden text-ellipsis">Temp {temp}</div>
      <CalendarCard />
    </div>
  );
}


