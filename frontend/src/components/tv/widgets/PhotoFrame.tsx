"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { FEATURES } from "@/config/features";

type PhotosResp = { folder: string; items: string[] };

export function PhotoFrame() {
  const [items, setItems] = useState<string[]>([]);
  const [idx, setIdx] = useState(0);
  const [crossFade, setCrossFade] = useState(0); // 0..1
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fadeRef = useRef<number | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await apiFetch("/v1/tv/photos", { method: "GET" });
        const body = (await res.json()) as PhotosResp;
        setItems(body.items || []);
      } catch {}
    })();
    return () => { if (timerRef.current) clearInterval(timerRef.current); if (fadeRef.current) cancelAnimationFrame(fadeRef.current); };
  }, []);

  useEffect(() => {
    if (items.length === 0) return;
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      if (!FEATURES.FEATURE_REDUCE_MOTION) {
        // animate crossfade 800ms
        const start = performance.now();
        const step = (t: number) => {
          const p = Math.min(1, (t - start) / 800);
          setCrossFade(p);
          if (p < 1) fadeRef.current = requestAnimationFrame(step); else setIdx((i) => (i + 1) % items.length);
        };
        fadeRef.current = requestAnimationFrame(step);
      } else {
        setIdx((i) => (i + 1) % items.length);
      }
    }, 6000);
  }, [items.length]);

  const folder = "/shared_photos"; // backend returns base; keep default
  const cur = items[idx];
  const prev = items[(idx - 1 + items.length) % Math.max(items.length, 1)];
  const showPrev = !FEATURES.FEATURE_REDUCE_MOTION && crossFade < 1 && prev !== cur;

  const prevOpacity = useMemo(() => 1 - crossFade, [crossFade]);

  return (
    <div className="relative w-full h-full flex items-center justify-center">
      {showPrev && (
        <img src={`${folder}/${prev}`} alt="Previous" className="absolute max-w-full max-h-full rounded-3xl shadow-2xl" style={{ opacity: prevOpacity }} />
      )}
      {cur ? (
        <img src={`${folder}/${cur}`} alt="Photo" className="relative max-w-full max-h-full rounded-3xl shadow-2xl" />
      ) : (
        <div className="text-white/70 text-[48px]">No photos found</div>
      )}
    </div>
  );
}


