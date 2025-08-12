"use client";
import React, { useState } from "react";
import { apiFetch } from "@/lib/api";

export default function IngestPage() {
    const [url, setUrl] = useState("");
    const [file, setFile] = useState<File | null>(null);
    const [status, setStatus] = useState<string>("");
    const [res, setRes] = useState<any>(null);

    async function onSubmit(e: React.FormEvent) {
        e.preventDefault();
        setStatus("Ingesting...");
        setRes(null);
        try {
            const form = new FormData();
            if (file) form.append("file", file);
            if (url) form.append("url", url);
            form.append("source", url || (file?.name || "upload"));
            const resp = await apiFetch("/v1/memory/ingest", { method: "POST", body: form, auth: true });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data?.detail || "Ingest failed");
            setRes(data);
            setStatus("Done");
        } catch (e: any) {
            setStatus(e?.message || String(e));
        }
    }

    return (
        <div className="max-w-2xl mx-auto p-6 space-y-6">
            <h1 className="text-2xl font-semibold">Memory Ingest</h1>
            <form onSubmit={onSubmit} className="space-y-4">
                <div>
                    <label className="block text-sm font-medium mb-1">URL</label>
                    <input className="w-full border rounded p-2" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://..." />
                </div>
                <div>
                    <label className="block text-sm font-medium mb-1">Or upload file</label>
                    <input type="file" onChange={e => setFile(e.target.files?.[0] || null)} />
                </div>
                <button className="px-4 py-2 bg-blue-600 text-white rounded" type="submit">Ingest</button>
            </form>
            {status && <div className="text-sm text-gray-600">{status}</div>}
            {res && (
                <div className="border rounded p-3 text-sm">
                    <div>doc_hash: {res.doc_hash}</div>
                    <div>chunk_count: {res.chunk_count}</div>
                    <div>ids: {(res.ids || []).join(", ")}</div>
                    <div>headings:</div>
                    <ul className="list-disc pl-4">
                        {(res.headings || []).map((h: string, i: number) => <li key={i}>{h}</li>)}
                    </ul>
                </div>
            )}
        </div>
    );
}


