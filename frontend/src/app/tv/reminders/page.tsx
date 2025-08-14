"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";

export default function Reminders() {
    const [items, setItems] = useState<string[]>([]);
    const [text, setText] = useState("");
    return (
        <main className="min-h-screen bg-black text-white p-8 max-w-3xl mx-auto">
            <h1 className="text-4xl font-bold mb-6">Reminders</h1>
            <div className="flex gap-4 mb-6">
                <input className="flex-1 text-black p-4 rounded" placeholder="eg. Take meds at 9" value={text} onChange={e => setText(e.target.value)} />
                <button className="bg-white text-black px-6 py-4 rounded-2xl text-2xl" onClick={async () => {
                    const t = text.trim();
                    if (!t) return;
                    try {
                        await apiFetch(`/v1/reminders`, { method: 'POST', body: JSON.stringify({ text: t, when: new Date().toISOString() }) });
                    } catch { }
                    setItems([t, ...items]); setText("");
                }}>Add</button>
            </div>
            <ul className="space-y-3 text-2xl">
                {items.map((it, i) => (<li key={i} className="bg-zinc-800 rounded-xl p-4">{it}</li>))}
            </ul>
        </main>
    );
}


