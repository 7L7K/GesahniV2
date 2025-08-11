"use client";
import React from "react";
import { useProfile } from "../hooks/useProfile";
import { useMetrics } from "../hooks/useMetrics";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Chat } from "../components/chat/Chat";

export default function Home() {
    const { data: profile } = useProfile();
    const { data: metrics } = useMetrics();

    return (
        <div style={{ padding: "var(--space-6)" }}>
            <h1 style={{ margin: 0 }}>Gesahni</h1>
            <p aria-live="polite" aria-atomic="true">
                {metrics ? `Total: ${metrics.metrics.total}, Cache hit rate: ${metrics.cache_hit_rate}%` : "Loading metrics..."}
            </p>

            <section aria-labelledby="profile-h">
                <h2 id="profile-h">Profile</h2>
                <div>
                    <label htmlFor="name">Name</label>
                    <Input id="name" defaultValue={profile?.name || ""} aria-describedby="name-hint" />
                    <div id="name-hint" aria-hidden="true" style={{ color: "var(--color-muted)", fontSize: 12 }}>
                        Your display name
                    </div>
                </div>
                <div style={{ marginTop: "var(--space-3)" }}>
                    <Button variant="primary">Save</Button>
                </div>
            </section>
            <Chat />
        </div>
    );
}


