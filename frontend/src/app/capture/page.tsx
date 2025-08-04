import type { Metadata } from "next";
import CaptureMode from "@/components/CaptureMode";

export const metadata: Metadata = {
  title: "Capture - Gesahni",
  description: "Start a new capture session with Gesahni.",
};

export default function CapturePage() {
  return <CaptureMode />;
}

