"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

type WeatherPayload = {
  city?: string;
  now?: { temp?: number | null; desc?: string | null; sentence?: string | null };
  today?: { high?: number; low?: number };
  tomorrow?: { high?: number; low?: number };
};

export function WeatherPeek() {
  const [data, setData] = useState<WeatherPayload | null>(null);
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    (async () => {
      try {
        const res = await apiFetch("/v1/tv/weather", { method: "GET" });
        const body = (await res.json()) as WeatherPayload;
        setData(body);
      } catch {
        setOffline(true);
      }
    })();
  }, []);

  const tiles = [
    { d: "Now", t: data?.now?.temp ? `${Math.round(data.now.temp)}°F` : "—", note: data?.now?.desc || "" },
    { d: "Today", t: data?.today?.high ? `${data.today.high}°/${data.today.low}°F` : "—", note: "" },
    { d: "Tomorrow", t: data?.tomorrow?.high ? `${data.tomorrow.high}°/${data.tomorrow.low}°F` : "—", note: "" },
  ];

  return (
    <div className="text-white w-full">
      <div className="grid grid-cols-3 gap-6">
        {tiles.map((f, i) => (
          <div key={i} className="bg-white/10 rounded-3xl p-10 text-center">
            <div className="text-[32px] mb-3">{f.d}</div>
            <div className="text-[64px] font-bold">{f.t}</div>
            {f.note && <div className="text-[28px] opacity-75 mt-3">{f.note}</div>}
          </div>
        ))}
      </div>
      <div className="mt-6 text-[28px]">
        {offline ? (
          <span>I didn’t catch the weather. Try the blue button.</span>
        ) : (
          <span>{data?.now?.sentence || ""}</span>
        )}
      </div>
    </div>
  );
}


