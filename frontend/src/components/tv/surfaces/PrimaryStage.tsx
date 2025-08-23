"use client";

import { scheduler } from "@/services/scheduler";
import { useEffect, useSyncExternalStore } from "react";
import { PhotoFrame } from "@/components/tv/widgets/PhotoFrame";
import { TranscriptSlate } from "@/components/tv/widgets/TranscriptSlate";
import { WeatherPeek } from "@/components/tv/widgets/WeatherPeek";
import { VitalsBadge } from "@/components/tv/widgets/VitalsBadge";
import { AlertPanel } from "@/components/tv/widgets/AlertPanel";
import { NowPlayingCard } from "@/components/tv/widgets/NowPlayingCard";
import { CalendarCard } from "@/components/tv/widgets/CalendarCard";

function useScheduler() {
  return useSyncExternalStore((cb) => {
    const t = setInterval(cb, 250);
    return () => clearInterval(t);
  }, () => scheduler.getAssignment(), () => scheduler.getAssignment());
}

export function PrimaryStage() {
  const assign = useScheduler();
  useEffect(() => { scheduler.start(); return () => scheduler.stop(); }, []);
  const id = assign.primary;
  return (
    <div className="relative w-full h-full flex items-center justify-center p-10">
      {id === "PhotoFrame" && <PhotoFrame />}
      {id === "TranscriptSlate" && <TranscriptSlate />}
      {id === "WeatherPeek" && <WeatherPeek />}
      {id === "VitalsBadge" && <VitalsBadge />}
      {id === "AlertPanel" && <AlertPanel />}
      {id === "NowPlayingCard" && <NowPlayingCard />}
      {id === "CalendarCard" && <CalendarCard />}
    </div>
  );
}
