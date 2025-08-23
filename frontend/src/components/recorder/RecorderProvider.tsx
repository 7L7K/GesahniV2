"use client";

import React, { createContext, useContext } from "react";
import { useRecorder, RecorderExports } from "./useRecorder";

const RecorderCtx = createContext<RecorderExports | null>(null);

export function RecorderProvider({ children }: { children: React.ReactNode }) {
    const rec = useRecorder();
    return <RecorderCtx.Provider value={rec}>{children}</RecorderCtx.Provider>;
}

export function useRecorderCtx(): RecorderExports {
    const ctx = useContext(RecorderCtx);
    if (!ctx) throw new Error("RecorderProvider missing");
    return ctx;
}
