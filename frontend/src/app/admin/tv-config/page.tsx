"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { getTvConfig, putTvConfig, TvConfig } from "@/lib/api";
import { scheduler } from "@/services/scheduler";

function validate(cfg: Partial<TvConfig>): string | null {
  if (cfg.ambient_rotation !== undefined && (cfg.ambient_rotation < 0 || cfg.ambient_rotation > 360)) return "ambient_rotation must be 0..360";
  if (cfg.rail && !["safe", "admin", "open"].includes(cfg.rail)) return "rail must be safe|admin|open";
  const hhmm = (s?: string) => !s || /^\d{2}:\d{2}$/.test(s);
  if (cfg.quiet_hours && (!hhmm(cfg.quiet_hours.start) || !hhmm(cfg.quiet_hours.end))) return "quiet_hours must be HH:MM";
  if (cfg.default_vibe !== undefined && typeof cfg.default_vibe !== 'string') return "default_vibe must be a string";
  return null;
}

function ExamplePreview({ cfg }: { cfg: TvConfig | null }) {
  // Lightweight preview: show how scheduler would pick in the next 120s by ticking locally
  const [frames, setFrames] = useState<string[]>([]);
  useEffect(() => {
    // snapshot current assignment every 3s for 120s
    const lines: string[] = [];
    const t = setInterval(() => {
      const a = scheduler.getAssignment();
      lines.push(`${new Date().toLocaleTimeString()} → primary=${a.primary} side=[${a.sideRail.join(', ')}]`);
      if (lines.length >= 40) {
        clearInterval(t);
        setFrames([...lines]);
      }
    }, 3000);
    scheduler.start();
    return () => { clearInterval(t); scheduler.stop(); };
  }, [cfg]);
  return (
    <div className="rounded border h-[520px] overflow-auto bg-white dark:bg-zinc-900 p-3 text-sm whitespace-pre-wrap">
      {frames.length ? frames.join("\n") : "Preview running…"}
    </div>
  );
}

export default function AdminTvConfigPage() {
  const [residentId, setResidentId] = useState<string>("r1");
  const [token, setToken] = useState<string>("");
  const [raw, setRaw] = useState<string>(`
{
  "ambient_rotation": 30,
  "rail": "safe",
  "quiet_hours": { "start": "22:00", "end": "06:00" },
  "default_vibe": "Calm Night"
}`);
  const [cfg, setCfg] = useState<TvConfig | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const envTok = process.env.NEXT_PUBLIC_ADMIN_TOKEN || '';
    const lsTok = typeof window !== 'undefined' ? (localStorage.getItem('admin:token') || '') : '';
    setToken(envTok || lsTok);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const res = await getTvConfig(residentId, token);
        setCfg(res.config);
        setRaw(JSON.stringify(res.config, null, 2));
        setErr(null);
      } catch (e: any) {
        setErr(e?.message || 'Load failed');
      }
    })();
  }, [residentId, token]);

  const onChangeRaw = (s: string) => {
    setRaw(s);
    try {
      const parsed = JSON.parse(s) as Partial<TvConfig>;
      const v = validate(parsed);
      if (v) { setErr(v); return; }
      setErr(null);
    } catch (e) {
      setErr('Invalid JSON');
    }
  };

  const onSave = async () => {
    try {
      const next = JSON.parse(raw) as TvConfig;
      const v = validate(next);
      if (v) { setErr(v); return; }
      setSaving(true);
      const res = await putTvConfig(residentId, token, next);
      setCfg(res.config);
      setErr(null);
      // Connect WS and wait for ack event
      try {
        const base = (process.env.NEXT_PUBLIC_API_BASE || '').replace(/^http/, 'ws');
        const ws = new WebSocket(`${base}/v1/ws/care`);
        wsRef.current = ws;
        ws.onopen = () => ws.send(JSON.stringify({ action: 'subscribe', topic: `resident:${residentId}` }));
        const to = setTimeout(() => { try { ws.close(); } catch {} }, 3000);
        ws.onmessage = (ev) => {
          try {
            const msg = JSON.parse(ev.data);
            if (msg?.data?.event === 'tv.config.updated' || msg?.event === 'tv.config.updated') {
              clearTimeout(to);
              ws.close();
            }
          } catch {}
        };
      } catch {}
    } catch (e: any) {
      setErr(e?.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 space-y-6">
      <h1 className="text-2xl font-semibold">TV Config Editor</h1>
      <div className="flex items-center gap-3 text-sm">
        <label className="text-xs text-muted-foreground">Resident</label>
        <input value={residentId} onChange={(e) => setResidentId(e.target.value)} className="border rounded px-2 py-1" />
        <label className="text-xs text-muted-foreground ml-4">Admin token</label>
        <input
          value={token}
          onChange={(e) => setToken(e.target.value)}
          onBlur={() => { try { localStorage.setItem('admin:token', token || '') } catch { } }}
          className="border rounded px-2 py-1 min-w-56"
          placeholder="paste token"
        />
        <button className="border rounded px-2 py-1 text-xs" onClick={() => { try { localStorage.setItem('admin:token', token || '') } catch { } }}>Save</button>
      </div>
      <div className="grid grid-cols-2 gap-6 items-start">
        <div className="space-y-2">
          <div className="text-sm text-muted-foreground">Edit JSON (schema-validated)</div>
          <textarea
            value={raw}
            onChange={(e) => onChangeRaw(e.target.value)}
            className="w-full h-[520px] font-mono text-sm border rounded p-3"
            spellCheck={false}
          />
          <div className="flex items-center gap-3">
            <button disabled={!!err || saving} onClick={onSave} className="border rounded px-4 py-2 text-sm disabled:opacity-50">
              {saving ? 'Saving…' : 'Save & Apply'}
            </button>
            {err && <div className="text-sm text-red-600">{err}</div>}
          </div>
        </div>
        <div className="space-y-2">
          <div className="text-sm text-muted-foreground">Live Preview (next 120s)</div>
          <ExamplePreview cfg={cfg} />
        </div>
      </div>
    </main>
  );
}


