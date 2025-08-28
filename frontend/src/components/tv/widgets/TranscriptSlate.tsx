"use client";

import { useEffect, useMemo, useState } from "react";
import { wsUrl } from "@/lib/api";
import { useSceneManager } from "@/state/sceneManager";

export function TranscriptSlate() {
  const [text, setText] = useState<string>("");
  const [isFinal, setIsFinal] = useState(false);
  const scene = useSceneManager();

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const delay = (n: number) => {
      const base = Math.min(30_000, 500 * Math.pow(2, n));
      // Avoid producing non-deterministic jitter during SSR; jitter is fine client-side
      const jitter = (typeof window !== 'undefined') ? base * (0.15 * (Math.random() * 2 - 1)) : 0;
      return Math.max(250, Math.floor(base + jitter));
    };

    const setup = () => {
      try { ws?.close(); } catch { }
      ws = new WebSocket(wsUrl("/v1/transcribe"));
      ws.onopen = () => { retry = 0; };
      ws.onmessage = (e) => {
        let msg: any = null;
        try { msg = JSON.parse(String(e.data || "")); } catch { msg = { text: String(e.data || "") }; }
        const t = String(msg.text || msg.partial || msg.final || "");
        const is_final = Boolean(msg.final || msg.is_final);
        setText(t);
        setIsFinal(is_final);
        (window as any).__lastTranscriptAt = Date.now();
        if (!is_final) {
          scene.toInteractive("stt_partial");
        } else {
          scene.toInteractive("stt_final");
        }
      };
      ws.onclose = () => {
        const d = delay(retry++);
        timer = setTimeout(() => setup(), d);
      };
      ws.onerror = () => { try { ws && ws.close(); } catch { } };
    };

    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        try { ws.send("ping"); } catch { }
        return;
      }
      if (timer) { clearTimeout(timer); timer = null; }
      retry = 0;
      setup();
    };

    setup();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
    window.addEventListener("focus", onVisible);

    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", onVisible);
      window.removeEventListener("focus", onVisible);
      if (timer) clearTimeout(timer);
      try { ws?.close(); } catch { }
    };
  }, [scene]);

  useEffect(() => { (window as any).__lastExchange = text; }, [text]);

  const clsHeader = "text-[64px] leading-[1.05] font-bold";
  const clsBody = "text-[32px] leading-snug";
  const label = isFinal ? "Heard" : "Hearing";

  const content = useMemo(() => text || "…", [text]);

  return (
    <div className="w-full h-full text-white">
      <div className="opacity-80 mb-6 text-[28px]">{label}</div>
      <div className={clsHeader}>{content}</div>
      <div className="mt-6 opacity-80">
        <div className={clsBody}>Say “help” anytime.</div>
      </div>
    </div>
  );
}
