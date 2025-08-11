"use client";
import React from "react";
import { useIsFetching } from "@tanstack/react-query";
import { Badge } from "../ui/Badge";

export function Header({ budgetRemaining }: { budgetRemaining?: string }) {
    const isFetching = useIsFetching();
    return (
        <header aria-label="Application header" className="sticky top-0 z-[var(--z-popover)] bg-surface/80 backdrop-blur border-b border-white/10">
            <div className="h-1 w-full bg-white/10">
                <div
                    className="h-1 bg-primary transition-all"
                    style={{ width: isFetching ? "60%" : "0%" }}
                    aria-hidden="true"
                />
            </div>
            <div className="flex items-center justify-between p-3 gap-3">
                <div className="text-sm text-muted">Gesahni</div>
                {budgetRemaining ? (
                    <Badge aria-label={`Budget remaining ${budgetRemaining}`} variant="neutral">Budget: {budgetRemaining}</Badge>
                ) : null}
            </div>
        </header>
    );
}


