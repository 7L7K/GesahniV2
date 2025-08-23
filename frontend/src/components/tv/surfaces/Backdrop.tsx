"use client";

import { useEffect, useRef } from "react";
import { FEATURES } from "@/config/features";

type Props = {
  dim?: number; // 0..1
  blur?: number; // px
  children?: React.ReactNode;
};

export function Backdrop({ dim = 0.25, blur = 8, children }: Props) {
  const animRef = useRef<number | null>(null);
  const laneRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (FEATURES.FEATURE_REDUCE_MOTION) return;
    const el = laneRef.current;
    if (!el) return;
    let x = 0;
    const dir = 1; // always forward, very slow
    const step = () => {
      x += 0.02 * dir; // px per frame
      el.style.backgroundPosition = `${x}px center`;
      animRef.current = requestAnimationFrame(step);
    };
    animRef.current = requestAnimationFrame(step);
    return () => { if (animRef.current) cancelAnimationFrame(animRef.current); };
  }, []);

  return (
    <div className="absolute inset-0 overflow-hidden">
      <div ref={laneRef} className="absolute inset-0" style={{
        backgroundImage: "linear-gradient(135deg, #0b1d3a 0%, #0a0a0a 60%, #1a0b2f 100%)",
        backgroundSize: "200% 100%",
        filter: `blur(${blur}px)`,
        transform: "scale(1.1)",
      }} />
      <div className="absolute inset-0" style={{ backgroundColor: `rgba(0,0,0,${dim})` }} />
      {children}
    </div>
  );
}
