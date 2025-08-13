"use client";

import { FEATURES } from "@/config/features";
import { useSceneManager } from "@/state/sceneManager";

export type WidgetId =
  | "PhotoFrame"
  | "TranscriptSlate"
  | "WeatherPeek"
  | "VitalsBadge"
  | "AlertPanel"
  | "NowPlayingCard"
  | "CalendarCard";

export type WidgetScore = {
  id: WidgetId;
  freshness: number; // 0..1
  importance: number; // 0..1
  timeRelevance: number; // 0..1
  prefs: number; // 0..1
  total: number; // computed
};

export type ScoreContext = {
  now: number;
  profile?: { font_scale?: number };
  lastExchangeText?: string;
  network?: { online: boolean; lastHeartbeatMs?: number };
};

export type Scorer = (id: WidgetId, ctx: ScoreContext) => Partial<WidgetScore> | void;

export type SchedulerAssignment = {
  primary: WidgetId | null;
  sideRail: WidgetId[];
  footerTicker: string | null;
  scores: WidgetScore[];
  nextEventChip: string | null;
};

const DEFAULT_WIDGETS: WidgetId[] = [
  "PhotoFrame",
  "TranscriptSlate",
  "WeatherPeek",
  "VitalsBadge",
  "AlertPanel",
  "NowPlayingCard",
  "CalendarCard",
];

function clamp01(n: number) { return Math.max(0, Math.min(1, n)); }

// Lightweight calendar cache updated by TV calendar fetchers
export type CalendarItem = { time?: string; title?: string; date?: string };
let _calendar: { items: CalendarItem[]; updatedAt?: number } = { items: [] };
export function _setCalendar(items: CalendarItem[]) {
  _calendar.items = Array.isArray(items) ? items : [];
  _calendar.updatedAt = Date.now();
}

function _parseTimeToDate(timeStr: string, base: Date): Date | null {
  // time like H:MM or HH:MM, assumed today
  if (!/^\d{1,2}:\d{2}$/.test(timeStr)) return null;
  const [h, m] = timeStr.split(":").map((s) => parseInt(s, 10));
  if (Number.isNaN(h) || Number.isNaN(m)) return null;
  const hh = Math.max(0, Math.min(23, h));
  const mm = Math.max(0, Math.min(59, m));
  const d = new Date(base);
  d.setHours(hh, mm, 0, 0);
  return d;
}

export class SchedulerService {
  private scorers: Scorer[] = [];
  private interval: ReturnType<typeof setInterval> | null = null;
  private lastAssignment: SchedulerAssignment = { primary: null, sideRail: [], footerTicker: null, scores: [], nextEventChip: null };
  private dryRunOverlayEl: HTMLDivElement | null = null;
  private forcedPrimary: { id: WidgetId; until: number } | null = null;
  private dwellHold: { id: WidgetId; until: number } | null = null;

  addScorer(s: Scorer) { this.scorers.push(s); }

  start() {
    if (!FEATURES.FEATURE_SCHEDULER_ON) return;
    // Always run an immediate tick to refresh assignment (idempotent)
    this.tick();
    if (this.interval) return;
    this.interval = setInterval(() => this.tick(), 3000);
  }

  stop() {
    if (this.interval) { clearInterval(this.interval); this.interval = null; }
    this.removeOverlay();
  }

  getAssignment(): SchedulerAssignment { return this.lastAssignment; }

  private computeScores(ctx: ScoreContext): WidgetScore[] {
    const scores: WidgetScore[] = [];
    for (const id of DEFAULT_WIDGETS) {
      let partial: Partial<WidgetScore> = {};
      for (const s of this.scorers) {
        try { const out = s(id, ctx); if (out) partial = { ...partial, ...out }; } catch { }
      }
      const freshness = clamp01(partial.freshness ?? 0.5);
      const importance = clamp01(partial.importance ?? (id === "AlertPanel" ? 1 : 0.5));
      const timeRelevance = clamp01(partial.timeRelevance ?? 0.5);
      const prefs = clamp01(partial.prefs ?? 0.5);
      const total = 0.40 * importance + 0.25 * timeRelevance + 0.20 * freshness + 0.15 * prefs;
      scores.push({ id, freshness, importance, timeRelevance, prefs, total });
    }
    scores.sort((a, b) => b.total - a.total);
    return scores;
  }

  private computeNextEventChip(nowMs: number): string | null {
    if (!_calendar.items.length) return null;
    const now = new Date(nowMs);
    // Assume items already for today onward. Choose first upcoming today by time.
    const mapped = _calendar.items
      .map((e) => ({
        when: _parseTimeToDate(e.time || "", now),
        title: String(e.title || ""),
      }));
    const upcoming = mapped
      .filter((e) => e.when && e.when.getTime() >= now.getTime())
      .sort((a, b) => (a.when!.getTime() - b.when!.getTime()));
    let first = upcoming[0];
    if (!first) {
      const any = mapped.filter((e) => e.when).sort((a, b) => (a.when!.getTime() - b.when!.getTime()));
      first = any[0];
    }
    if (!first || !first.when) return null;
    const hh = String(first.when.getHours()).padStart(2, "0");
    const mm = String(first.when.getMinutes()).padStart(2, "0");
    // Ensure stable formatting: 24h HH:MM
    return `Next: ${first.title} ${hh}:${mm}`;
  }

  private assign(scores: WidgetScore[]): SchedulerAssignment {
    const now = Date.now();
    let primary = scores[0]?.id || null;
    if (this.forcedPrimary && now < this.forcedPrimary.until) {
      primary = this.forcedPrimary.id;
    } else if (this.dwellHold && now < this.dwellHold.until) {
      primary = this.dwellHold.id;
    } else {
      this.forcedPrimary = null;
      this.dwellHold = null;
    }
    const sideRail = scores.slice(1, 4).map(s => s.id);
    const footerTicker = this.makeTicker();
    const nextEventChip = this.computeNextEventChip(Date.now());
    // If CalendarCard is selected as primary by score (not forced/dwell), set a dwell window
    const topByScore = scores[0]?.id || null;
    if (!this.forcedPrimary && (!this.dwellHold || now >= this.dwellHold.until) && topByScore === "CalendarCard") {
      const hour = new Date(now).getHours();
      const morningOrEarlyPm = (hour >= 7 && hour <= 15);
      const night = (hour >= 21 || hour <= 5);
      // dwell: 15–25s mornings/early PM, 6–10s night, otherwise 10–15s
      const dwellSec = morningOrEarlyPm ? (15 + Math.floor(Math.random() * 11)) : night ? (6 + Math.floor(Math.random() * 5)) : (10 + Math.floor(Math.random() * 6));
      this.dwellHold = { id: "CalendarCard", until: now + dwellSec * 1000 };
      primary = "CalendarCard";
    }
    return { primary, sideRail, footerTicker, scores, nextEventChip };
  }

  private makeTicker(): string | null {
    if (!FEATURES.FEATURE_TICKER) return null;
    const txt = (window as any).__lastExchange as string | undefined;
    if (!txt) return null;
    const clean = String(txt).replace(/\s+/g, " ").trim();
    if (clean.length === 0) return null;
    // Truncation rules: prefer word boundary ~ 140 chars
    if (clean.length <= 160) return clean;
    const cut = clean.slice(0, 160);
    const lastSpace = cut.lastIndexOf(" ");
    return (lastSpace > 80 ? cut.slice(0, lastSpace) : cut) + "…";
  }

  private ensureOverlay() {
    if (typeof document === "undefined") return;
    if (this.dryRunOverlayEl) return;
    const el = document.createElement("div");
    el.style.position = "fixed";
    el.style.bottom = "8px";
    el.style.right = "8px";
    el.style.zIndex = "9999";
    el.style.background = "rgba(0,0,0,0.6)";
    el.style.color = "#0f0";
    el.style.fontFamily = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace";
    el.style.padding = "6px 8px";
    el.style.borderRadius = "8px";
    el.style.maxWidth = "40vw";
    el.style.pointerEvents = "none";
    document.body.appendChild(el);
    this.dryRunOverlayEl = el;
  }

  private removeOverlay() {
    if (this.dryRunOverlayEl) {
      try { this.dryRunOverlayEl.remove(); } catch { }
      this.dryRunOverlayEl = null;
    }
  }

  private renderOverlay(assign: SchedulerAssignment) {
    if (!this.dryRunOverlayEl) return;
    const lines = [
      `scene=${useSceneManager.getState().scene}`,
      `primary=${assign.primary ?? "-"}`,
      `side=[${assign.sideRail.join(", ")}]`,
      `ticker=${assign.footerTicker ? assign.footerTicker.slice(0, 60) : "-"}`,
      `next=${assign.nextEventChip || "-"}`,
    ];
    this.dryRunOverlayEl!.innerText = lines.join("\n");
  }

  private tick() {
    const ctx: ScoreContext = { now: Date.now() };
    const scores = this.computeScores(ctx);
    const assign = this.assign(scores);
    this.lastAssignment = assign;
    if (process.env.NODE_ENV !== "production") {
      this.ensureOverlay();
      this.renderOverlay(assign);
    }
    // scene effects: selecting a new primary nudges interactive unless quiet hours
    const state = useSceneManager.getState();
    if (assign.primary && state.scene !== "alert" && !state.isQuietHours) {
      useSceneManager.getState().toInteractive("scheduler_primary_focus");
    }
  }

  // External nudges via remote
  nudge(direction: "prev" | "next") {
    const scores = this.lastAssignment.scores?.length ? this.lastAssignment.scores : this.computeScores({ now: Date.now() });
    if (!scores.length) return;
    const currentId = (this.lastAssignment.primary || scores[0].id);
    const idx = scores.findIndex(s => s.id === currentId);
    const nextIdx = (direction === "next") ? (idx + 1) % scores.length : (idx - 1 + scores.length) % scores.length;
    const id = scores[nextIdx].id;
    this.forcedPrimary = { id, until: Date.now() + 8000 };
  }
}

// Default instance and basic scorers -----------------------------------------
export const scheduler = new SchedulerService();

// Freshness: prefer TranscriptSlate when new tokens appear
scheduler.addScorer((id, ctx) => {
  if (id !== "TranscriptSlate") return;
  const age = (window as any).__lastTranscriptAt as number | undefined;
  if (!age) return;
  const secs = (ctx.now - age) / 1000;
  return { freshness: secs < 6 ? 1 : secs < 20 ? 0.7 : 0.3 };
});

// Importance: Alerts always top
scheduler.addScorer((id) => {
  if (id === "AlertPanel") return { importance: 1 };
  return;
});

// Time relevance: Weather higher in morning/evening
scheduler.addScorer((id) => {
  if (id !== "WeatherPeek") return;
  const hour = new Date().getHours();
  const boost = (hour >= 6 && hour <= 10) || (hour >= 17 && hour <= 20) ? 1 : 0.5;
  return { timeRelevance: boost };
});

// Calendar: boost mornings/early PM; lower at night; 45m pre-event priority
scheduler.addScorer((id) => {
  if (id !== "CalendarCard") return;
  const hour = new Date().getHours();
  const morningOrEarlyPm = (hour >= 7 && hour <= 13) || (hour >= 13 && hour <= 15);
  const night = (hour >= 21 || hour <= 5);
  const baseTime = morningOrEarlyPm ? 1 : night ? 0.3 : 0.6;
  // priority boost within 45 minutes of next event
  let importance = 0.5;
  try {
    const now = new Date();
    const upcoming = _calendar.items
      .map((e) => _parseTimeToDate(String(e.time || ""), now))
      .filter((d): d is Date => !!d)
      .sort((a, b) => a.getTime() - b.getTime())
      .find((d) => d.getTime() >= now.getTime());
    if (upcoming) {
      const diffMin = (upcoming.getTime() - now.getTime()) / 60000;
      if (diffMin <= 45) importance = 1;
    }
  } catch { }
  return { timeRelevance: baseTime, importance };
});

// Prefs: placeholder constant mid-weight
scheduler.addScorer((_id) => ({ prefs: 0.5 }));


