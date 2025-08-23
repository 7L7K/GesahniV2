"use client";

import { create } from "zustand";

export type WidgetKind =
  | "PhotoFrame"
  | "TranscriptSlate"
  | "WeatherPeek"
  | "VitalsBadge"
  | "AlertPanel"
  | "NowPlayingCard";

export interface WidgetMeta {
  id: WidgetKind;
  label: string;
  motionLevel: 0 | 1 | 2; // 0=static, 1=subtle, 2=high-motion
  enabled: boolean;
}

export interface RegistryState {
  items: Record<string, WidgetMeta>;
  // rule: max one high-motion element at a time
  allowsHighMotion: () => boolean;
  setEnabled: (id: WidgetKind, enabled: boolean) => void;
}

const defaults: WidgetMeta[] = [
  { id: "PhotoFrame", label: "Photos", motionLevel: 1, enabled: true },
  { id: "TranscriptSlate", label: "Transcript", motionLevel: 0, enabled: true },
  { id: "WeatherPeek", label: "Weather", motionLevel: 0, enabled: true },
  { id: "VitalsBadge", label: "Vitals", motionLevel: 0, enabled: true },
  { id: "AlertPanel", label: "Alerts", motionLevel: 2, enabled: true },
  { id: "NowPlayingCard", label: "Now Playing", motionLevel: 1, enabled: true },
];

export const useWidgetRegistry = create<RegistryState>((set, get) => ({
  items: Object.fromEntries(defaults.map((d) => [d.id, d])),
  allowsHighMotion: () => {
    const items = Object.values(get().items);
    const high = items.filter((i) => i.enabled && i.motionLevel === 2);
    return high.length <= 1;
  },
  setEnabled: (id, enabled) => set((s) => ({ items: { ...s.items, [id]: { ...s.items[id], enabled } } })),
}));
