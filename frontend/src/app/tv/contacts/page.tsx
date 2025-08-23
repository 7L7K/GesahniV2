"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { apiFetch } from "@/lib/api";

type Contact = { name: string; photo?: string };

export default function Contacts() {
    const [items, setItems] = useState<Contact[]>([]);
    const [toCall, setToCall] = useState<Contact | null>(null);
    const [message, setMessage] = useState<string>("");
    useEffect(() => {
        (async () => {
            try {
                const res = await apiFetch("/v1/tv/contacts", { method: "GET" });
                const body = (await res.json()) as { items: Contact[] };
                setItems(Array.isArray(body.items) ? body.items : []);
            } catch {
                setItems([]);
            }
        })();
    }, []);

    const confirm = async () => {
        if (!toCall) return;
        try {
            const res = await apiFetch(`/v1/tv/contacts/call`, { method: "POST", body: JSON.stringify({ name: toCall.name }) });
            const body = await res.json().catch(() => ({} as any));
            setMessage((body?.message as string) || "Pick up your phone, I’ll dial for you");
        } catch {
            setMessage("Pick up your phone, I’ll dial for you");
        } finally {
            setToCall(null);
            setTimeout(() => setMessage(""), 3000);
        }
    };

    return (
        <main className="min-h-screen bg-black text-white p-8 max-w-5xl mx-auto">
            <h1 className="text-6xl font-bold mb-8">Family Contacts</h1>
            <div className="grid grid-cols-2 gap-6">
                {items.map((c) => (
                    <button key={c.name} onClick={() => setToCall(c)} className="bg-zinc-800 rounded-3xl p-6 text-left text-4xl flex items-center gap-6 focus:outline-none focus:ring-8 focus:ring-blue-500">
                        {c.photo ? (
                            <Image src={c.photo} alt={c.name} width={96} height={96} className="rounded-full object-cover" />
                        ) : (
                            <div className="w-24 h-24 rounded-full bg-zinc-700 flex items-center justify-center text-3xl">👤</div>
                        )}
                        <span>Call {c.name}</span>
                    </button>
                ))}
                {items.length === 0 && <div className="text-3xl opacity-80">No contacts yet.</div>}
            </div>

            {toCall && (
                <div className="fixed inset-0 bg-black/60 flex items-center justify-center">
                    <div className="bg-zinc-900 p-10 rounded-3xl text-center space-y-6">
                        <div className="text-5xl">Call {toCall.name}?</div>
                        <div className="flex gap-8 justify-center">
                            <button onClick={confirm} className="bg-green-600 px-10 py-6 rounded-3xl text-4xl">Yes</button>
                            <button onClick={() => setToCall(null)} className="bg-red-700 px-10 py-6 rounded-3xl text-4xl">No</button>
                        </div>
                    </div>
                </div>
            )}

            {message && <div className="mt-8 text-3xl">{message}</div>}
        </main>
    );
}
