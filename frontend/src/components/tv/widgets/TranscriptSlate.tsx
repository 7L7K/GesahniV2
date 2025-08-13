"use client";

import { useEffect, useMemo, useState } from "react";
import { wsUrl } from "@/lib/api";
import { useSceneManager } from "@/state/sceneManager";

export function TranscriptSlate() {
  const [text, setText] = useState<string>("");
  const [isFinal, setIsFinal] = useState(false);
  const scene = useSceneManager();

  useEffect(() => {
    const ws = new WebSocket(wsUrl("/v1/transcribe"));
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
    return () => { try { ws.close(); } catch {} };
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


