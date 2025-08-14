import type { Metadata } from "next";
import CaptureMode from "@/components/CaptureMode";
import { redirect } from "next/navigation";
import { cookies } from "next/headers";

export const metadata: Metadata = {
  title: "Capture - Gesahni",
  description: "Start a new capture session with Gesahni.",
};

export default async function CapturePage() {
  // Server component guard: rely on cookie hint or fall back to client check
  // Since tokens are in localStorage, we cannot fully verify here; perform a soft guard
  // by reading an opt-in cookie set by client after login. If absent, still render,
  // but CaptureMode will handle client-side redirect.
  const cookieStore = await cookies();
  const authedHint = cookieStore.get('auth_hint')?.value;
  if (authedHint === '0') {
    redirect('/login?next=%2Fcapture');
  }
  return <CaptureMode />;
}

