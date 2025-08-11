"use client";
import React, { useMemo, useRef, useState } from "react";
import { Input } from "../ui/Input";
import { Button } from "../ui/Button";

type Msg = { role: "user" | "assistant"; text: string };

export function Chat() {
    const [messages, setMessages] = useState<Msg[]>([]);
    const [prompt, setPrompt] = useState("");
    const [loading, setLoading] = useState(false);
    const abortRef = useRef<AbortController | null>(null);

    const onStop = () => {
        abortRef.current?.abort();
    };

    const submit = async () => {
        const q = prompt.trim();
        if (!q) return;
        setPrompt("");
        setMessages((m) => [...m, { role: "user", text: q }, { role: "assistant", text: "" }]);
        setLoading(true);
        const ctrl = new AbortController();
        abortRef.current = ctrl;
        try {
            const accept = "text/event-stream";
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/v1/ask`, {
                method: "POST",
                headers: { "Content-Type": "application/json", Accept: accept },
                body: JSON.stringify({ prompt: q }),
                signal: ctrl.signal,
            });
            if (!res.ok || !res.body) throw new Error("Request failed");
            const reader = res.body.getReader();
            const dec = new TextDecoder();
            let assistantText = "";
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const chunk = dec.decode(value);
                const lines = chunk.split("\n\n");
                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed) continue;
                    // SSE framing: data: <payload>
                    const data = trimmed.startsWith("data:") ? trimmed.slice(5).trim() : trimmed;
                    assistantText += data;
                    setMessages((m) => {
                        const copy = [...m];
                        copy[copy.length - 1] = { role: "assistant", text: assistantText };
                        return copy;
                    });
                }
            }
        } catch (e) {
            // aborted or error
        } finally {
            setLoading(false);
            abortRef.current = null;
        }
    };

    return (
        <section aria-labelledby="chat-h" className="grid gap-3">
            <h2 id="chat-h">Chat</h2>
            <div aria-live="polite" aria-atomic="false" className="grid gap-2">
                {messages.length === 0 && (
                    <div role="status" className="opacity-70">Ask something to get started…</div>
                )}
                {messages.map((m, i) => (
                    <div key={i} className="rounded-md p-3 bg-surface border border-white/10">
                        <span className="text-muted text-xs" aria-hidden="true">{m.role}</span>
                        <div>{m.text || (loading && i === messages.length - 1 ? <SkeletonLines /> : null)}</div>
                    </div>
                ))}
            </div>
            <div className="flex gap-2 items-center">
                <label htmlFor="prompt" className="sr-only">Prompt</label>
                <Input id="prompt" value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Ask…" onKeyDown={(e) => (e.key === "Enter" ? submit() : undefined)} />
                <Button onClick={submit} aria-label="Send" disabled={loading && !!abortRef.current}>Send</Button>
                <Button onClick={onStop} variant="ghost" aria-label="Stop generating" disabled={!loading}>Stop</Button>
            </div>
        </section>
    );
}

function SkeletonLines() {
    return (
        <div aria-hidden className="grid gap-2">
            <div className="h-3 w-48 bg-white/10 rounded" />
            <div className="h-3 w-72 bg-white/10 rounded" />
            <div className="h-3 w-56 bg-white/10 rounded" />
        </div>
    );
}


