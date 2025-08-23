export type FeatureFlags = {
  FEATURE_SCHEDULER_ON: boolean;
  FEATURE_REDUCE_MOTION: boolean;
  FEATURE_TICKER: boolean;
};

function flag(name: string, fallback = false): boolean {
  if (typeof process === "undefined" || !process.env) return fallback;
  const v = (process.env as Record<string, string | undefined>)[`NEXT_PUBLIC_${name}`];
  if (!v) return fallback;
  const s = String(v).toLowerCase();
  return s === "1" || s === "true" || s === "yes" || s === "on";
}

export const FEATURES: FeatureFlags = {
  FEATURE_SCHEDULER_ON: flag("FEATURE_SCHEDULER_ON", true),
  FEATURE_REDUCE_MOTION: flag("FEATURE_REDUCE_MOTION", false),
  FEATURE_TICKER: flag("FEATURE_TICKER", true),
};
