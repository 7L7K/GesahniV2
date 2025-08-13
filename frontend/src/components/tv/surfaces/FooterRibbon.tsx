"use client";

import { scheduler } from "@/services/scheduler";
import { useEffect, useSyncExternalStore } from "react";
import { FEATURES } from "@/config/features";

function useScheduler() {
  return useSyncExternalStore((cb) => { const t = setInterval(cb, 250); return () => clearInterval(t); }, () => scheduler.getAssignment(), () => scheduler.getAssignment());
}

export function FooterRibbon() {
  const assign = useScheduler();
  useEffect(() => { scheduler.start(); return () => scheduler.stop(); }, []);
  if (!FEATURES.FEATURE_TICKER) return null;
  const text = assign.footerTicker;
  if (!text) return null;
  return (
    <div className="absolute left-0 right-0 bottom-0 bg-black/70 text-white">
      <div className="mx-auto max-w-[90vw] py-3 text-[28px] leading-tight truncate">
        {text}
      </div>
    </div>
  );
}


