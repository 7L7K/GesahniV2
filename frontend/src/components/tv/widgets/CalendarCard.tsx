"use client";

import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";

export type CalendarItem = {
  time?: string; // "HH:MM"
  title?: string;
  startIso?: string; // optional ISO start
  travelMinutes?: number | null; // optional travel estimate
  bufferMinutes?: number | null; // optional buffer
};

type CalendarNextRes = { items: CalendarItem[]; updatedAt?: string };

function parseTimeToToday(time: string | undefined): Date | null {
  if (!time) return null;
  const [hh, mm] = time.split(":").map((s) => parseInt(s, 10));
  if (Number.isNaN(hh) || Number.isNaN(mm)) return null;
  const d = new Date();
  d.setSeconds(0, 0);
  d.setHours(hh, mm, 0, 0);
  return d;
}

function fmtHM(d: Date): string {
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function computeLeaveBy(now: Date, item: CalendarItem): string | null {
  const travelRaw = item.travelMinutes;
  const travel = typeof travelRaw === "number" ? travelRaw : null;
  if (travel === null || travel <= 0) return null;
  const buffer = Math.max(0, item.bufferMinutes ?? 0);
  // Establish event start: prefer startIso then time today
  let start: Date | null = null;
  if (item.startIso) {
    const s = new Date(item.startIso);
    if (!Number.isNaN(s.getTime())) start = s;
  }
  if (!start) start = parseTimeToToday(item.time);
  if (!start) return null;
  const startMinusBuffer = new Date(start.getTime() - buffer * 60_000);
  const leaveBy = new Date(startMinusBuffer.getTime() - travel * 60_000);
  // Always compute leave-by when travel is known
  return fmtHM(leaveBy);
}

export function CalendarCard() {
  const [items, setItems] = useState<CalendarItem[]>([]);
  // Avoid initializing Date on server; set on mount
  const [now, setNow] = useState<Date | null>(null);
  const [mounted, setMounted] = useState<boolean>(false);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const res = (await apiFetch("/v1/tv/calendar/next", { method: "GET" }).then((r) => r.json())) as CalendarNextRes;
        if (mounted) setItems(Array.isArray(res.items) ? res.items : []);
      } catch {
        if (mounted) setItems([]);
      }
    })();
    const t = setInterval(() => setNow(new Date()), 30_000);
    // initialize now and mark mounted to prevent SSR/client mismatch
    setNow(new Date());
    setMounted(true);
    return () => {
      mounted = false;
      clearInterval(t);
    };
  }, []);

  const first = items[0];
  const leaveBy = useMemo(() => (first && now ? computeLeaveBy(now, first) : null), [now, first]);

  if (!first) {
    return (
      <div className="bg-white/10 rounded-2xl px-6 py-4 text-[28px] text-white">
        No upcoming events
      </div>
    );
  }

  return (
    <div className="bg-white/10 rounded-2xl px-6 py-4 text-white">
      <div className="text-[22px] opacity-80">Next</div>
      <div className="text-[28px] whitespace-nowrap overflow-hidden text-ellipsis">{first.time || ""} {first.title || ""}</div>
      {leaveBy && (
        <div className="mt-2 text-[24px] text-yellow-200">Leave by {leaveBy}</div>
      )}
    </div>
  );
}

export const __test = { parseTimeToToday, computeLeaveBy };
