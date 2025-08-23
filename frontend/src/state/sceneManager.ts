"use client";

import { create } from "zustand";

export type Scene = "ambient" | "interactive" | "alert";

export type SceneTransitionCause =
  | "user_interaction"
  | "scheduler_primary_focus"
  | "ws_alert"
  | "stt_partial"
  | "stt_final"
  | "timeout_auto_return"
  | "quiet_hours";

export interface SceneState {
  scene: Scene;
  lastTransitionAt: number; // epoch ms
  lastCause: SceneTransitionCause | null;
  isQuietHours: boolean;
  // 8s auto-return timer id (if set)
  autoTimer: ReturnType<typeof setTimeout> | null;

  // guarded transitions
  toAmbient: (cause: SceneTransitionCause) => void;
  toInteractive: (cause: SceneTransitionCause) => void;
  toAlert: (cause: SceneTransitionCause) => void;
  setQuietHours: (on: boolean) => void;
}

const AUTO_RETURN_MS = 8000;

function now() { return Date.now(); }

function clearTimer(timer: ReturnType<typeof setTimeout> | null) {
  if (timer) clearTimeout(timer);
}

export const useSceneManager = create<SceneState>((set, get) => ({
  scene: "ambient",
  lastTransitionAt: now(),
  lastCause: null,
  isQuietHours: false,
  autoTimer: null,

  toAmbient: (cause) => {
    const current = get().scene;
    if (current === "alert") return; // alert holds control until dismissed
    clearTimer(get().autoTimer);
    set({ scene: "ambient", lastTransitionAt: now(), lastCause: cause, autoTimer: null });
  },

  toInteractive: (cause) => {
    const current = get().scene;
    if (current === "alert") return; // cannot enter interactive during alert
    clearTimer(get().autoTimer);
    const timer = setTimeout(() => {
      // auto-return to ambient
      const s = get();
      if (s.scene === "interactive") {
        set({ scene: "ambient", lastTransitionAt: now(), lastCause: "timeout_auto_return", autoTimer: null });
      }
    }, AUTO_RETURN_MS);
    set({ scene: "interactive", lastTransitionAt: now(), lastCause: cause, autoTimer: timer });
  },

  toAlert: (cause) => {
    clearTimer(get().autoTimer);
    set({ scene: "alert", lastTransitionAt: now(), lastCause: cause, autoTimer: null });
  },

  setQuietHours: (on) => set({ isQuietHours: on }),
}));

export function useScene(): SceneState {
  return useSceneManager();
}
