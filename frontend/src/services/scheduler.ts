"use client";

import { FEATURES } from "@/config/features";
import { useSceneManager } from "@/state/sceneManager";

export type WidgetId =
  | "PhotoFrame"
  | "TranscriptSlate"
  | "WeatherPeek"
  | "VitalsBadge"
  | "AlertPanel"
  | "NowPlayingCard";

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
};

const DEFAULT_WIDGETS: WidgetId[] = [
  "PhotoFrame",
  "TranscriptSlate",
  "WeatherPeek",
  "VitalsBadge",
  "AlertPanel",
  "NowPlayingCard",
];

function clamp01(n: number) { return Math.max(0, Math.min(1, n)); }

export class SchedulerService {
  private scorers: Scorer[] = [];
  private interval: ReturnType<typeof setInterval> | null = null;
  private lastAssignment: SchedulerAssignment = { primary: null, sideRail: [], footerTicker: null, scores: [] };
  private dryRunOverlayEl: HTMLDivElement | null = null;
  private forcedPrimary: { id: WidgetId; until: number } | null = null;

  addScorer(s: Scorer) { this.scorers.push(s); }

  start() {
    if (!FEATURES.FEATURE_SCHEDULER_ON) return;
    if (this.interval) return;
    this.tick();
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

  private assign(scores: WidgetScore[]): SchedulerAssignment {
    let primary = scores[0]?.id || null;
    if (this.forcedPrimary && Date.now() < this.forcedPrimary.until) {
      primary = this.forcedPrimary.id;
    } else {
      this.forcedPrimary = null;
    }
    const sideRail = scores.slice(1, 4).map(s => s.id);
    const footerTicker = this.makeTicker();
    return { primary, sideRail, footerTicker, scores };
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

// Prefs: placeholder constant mid-weight
scheduler.addScorer((_id) => ({ prefs: 0.5 }));


