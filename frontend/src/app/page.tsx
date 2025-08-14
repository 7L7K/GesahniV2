'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import ChatBubble from '../components/ChatBubble';
import LoadingBubble from '../components/LoadingBubble';
import InputBar from '../components/InputBar';
import { Button } from '@/components/ui/button';
import { SignedIn, SignedOut, SignInButton, SignUpButton, useUser, useAuth } from '@clerk/nextjs';
import { sendPrompt, getToken, getMusicState, type MusicState } from '@/lib/api';
import { wsHub } from '@/services/wsHub';
import NowPlayingCard from '@/components/music/NowPlayingCard';
import DiscoveryCard from '@/components/music/DiscoveryCard';
import MoodDial from '@/components/music/MoodDial';
import QueueCard from '@/components/music/QueueCard';
import DevicePicker from '@/components/music/DevicePicker';
import { RateLimitToast } from '@/components/ui/toast';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  loading?: boolean;
}

export default function Page() {
  const router = useRouter();
  const [authed, setAuthed] = useState<boolean>(false);
  const [isOnline, setIsOnline] = useState<boolean>(true);
  const [sessionReady, setSessionReady] = useState<boolean>(false);
  const [backendOffline, setBackendOffline] = useState<boolean>(false);
  const [hasAccessCookie, setHasAccessCookie] = useState<boolean>(false);
  const [whoamiOk, setWhoamiOk] = useState<boolean>(false);
  const authBootOnce = useRef<boolean>(false);
  const finishOnceRef = useRef<boolean>(false);
  const [finishBusy, setFinishBusy] = useState<boolean>(false);
  const [finishError, setFinishError] = useState<string | null>(null);
  const finishAbortRef = useRef<AbortController | null>(null);
  const prevReadyRef = useRef<boolean>(false);
  const prevBackendOnlineRef = useRef<boolean | null>(null);
  const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
  const { isSignedIn } = useUser();
  const { isLoaded } = useAuth();
  const createInitialMessage = (): ChatMessage => ({
    id: crypto.randomUUID(),
    role: 'assistant',
    content: "Hey King, what’s good?",
  });

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [musicState, setMusicState] = useState<MusicState | null>(null);
  // 'auto' lets the backend route to skills/LLM; user can still force a model
  const [model, setModel] = useState('auto');
  const bottomRef = useRef<HTMLDivElement>(null);

  // Helpers: scope storage keys per user id for privacy
  const getScopedKey = (base: string): string => {
    try {
      const token = getToken();
      if (!token) return `${base}:guest`;
      const parts = token.split('.')
      if (parts.length >= 2 && typeof window !== 'undefined') {
        const json = JSON.parse(atob(parts[1]));
        const sub = json?.sub || json?.user_id || json?.uid || 'anon';
        return `${base}:${String(sub)}`;
      }
      return `${base}:anon`;
    } catch {
      return `${base}:anon`;
    }
  };
  const historyKey = getScopedKey('chat-history');
  const modelKey = getScopedKey('selected-model');

  // Helper to read cookie presence client-side
  const readHasAccessCookie = useCallback(() => {
    try { return typeof document !== 'undefined' && document.cookie.includes('access_token='); } catch { return false; }
  }, []);

  // Startup probe: ping healthz with a 2s timeout and backoff when offline
  useEffect(() => {
    let cancelled = false;
    let backoff = 2000;
    const ping = async () => {
      if (cancelled) return;
      try {
        const controller = new AbortController();
        const t = setTimeout(() => controller.abort(), 2000);
        const r = await fetch('/v1/healthz', { signal: controller.signal });
        clearTimeout(t);
        const ok = r && r.ok;
        setBackendOffline(!ok);
        window.dispatchEvent(new CustomEvent('auth:backend', { detail: { online: ok } }));
        if (prevBackendOnlineRef.current !== ok) {
          try { console.info(`AUTH backend: online=${ok}`); } catch { /* noop */ }
          prevBackendOnlineRef.current = ok;
        }
        if (!ok) {
          setTimeout(ping, backoff);
          backoff = Math.min(15000, Math.floor(backoff * 1.6));
        }
      } catch {
        setBackendOffline(true);
        window.dispatchEvent(new CustomEvent('auth:backend', { detail: { online: false } }));
        if (prevBackendOnlineRef.current !== false) {
          try { console.info(`AUTH backend: online=false`); } catch { /* noop */ }
          prevBackendOnlineRef.current = false;
        }
        setTimeout(ping, backoff);
        backoff = Math.min(15000, Math.floor(backoff * 1.6));
      }
    };
    ping();
    return () => { cancelled = true; };
  }, []);

  // Hydrate from localStorage on mount; if none, seed with initial assistant msg
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const hasHeaderToken = Boolean(getToken());
      const cookiePresent = readHasAccessCookie();
      setHasAccessCookie(cookiePresent);
      if (cookiePresent) {
        setAuthed(true);
      }
      if (hasHeaderToken) {
        setAuthed(true);
        setSessionReady(true);
      } else {
        // Cookie mode: rely on auth hint or backend whoami
        if (!authBootOnce.current) (async () => {
          try {
            const hinted = document.cookie.includes('auth_hint=1');
            if (hinted) {
              setAuthed(true);
              setSessionReady(true);
            } else {
              // Background whoami to hydrate, do not block UI
              try {
                const r = await fetch('/v1/whoami', { credentials: 'include' });
                if (r.ok) {
                  const b: any = await r.json().catch(() => ({}));
                  const ok = Boolean(b && (b.is_authenticated || (b.user_id && b.user_id !== 'anon')));
                  setAuthed(ok);
                  setWhoamiOk(ok);
                  window.dispatchEvent(new CustomEvent('auth:whoami', { detail: { ok } }));
                }
              } catch { /* ignore */ }
            }
          } catch {
            setAuthed(false);
          }
        })();
      }
      setIsOnline(navigator.onLine);
      const onUp = () => setIsOnline(true);
      const onDown = () => setIsOnline(false);
      window.addEventListener('online', onUp);
      window.addEventListener('offline', onDown);
      const stored = localStorage.getItem(historyKey);
      if (stored) {
        try {
          const parsed = JSON.parse(stored);
          // Validate that parsed data has the correct structure
          if (Array.isArray(parsed)) {
            type StoredMessage = Partial<ChatMessage> & { content?: unknown; role?: unknown };
            const validMessages: ChatMessage[] = (parsed as StoredMessage[])
              .filter((m) => m && typeof m === 'object' &&
                typeof m.content === 'string' &&
                (m.role === 'user' || m.role === 'assistant'))
              .map((m) => ({
                id: m.id ?? crypto.randomUUID(),
                role: m.role as 'user' | 'assistant',
                content: m.content as string,
                loading: Boolean(m.loading),
              }));
            setMessages(validMessages.length > 0 ? validMessages.slice(-100) : [createInitialMessage()]);
          } else {
            setMessages([createInitialMessage()]);
          }
        } catch {
          setMessages([createInitialMessage()]);
        }
      } else {
        setMessages([createInitialMessage()]);
      }

      // Also hydrate the model selection
      const storedModel = localStorage.getItem(modelKey);
      if (storedModel) {
        setModel(storedModel);
      }
      return () => {
        window.removeEventListener('online', onUp);
        window.removeEventListener('offline', onDown);
      }
    }
  }, [readHasAccessCookie]);

  // Compute readiness for Clerk: isSignedIn AND (cookie present OR whoami says ok)
  useEffect(() => {
    if (!clerkEnabled) return;
    const ready = Boolean(isSignedIn && (hasAccessCookie || whoamiOk));
    setSessionReady(ready);
    try { window.dispatchEvent(new CustomEvent('auth:ready', { detail: { ready } })); } catch { /* noop */ }
    if (prevReadyRef.current !== ready) {
      try {
        console.info(`AUTH ready: signedIn=${Boolean(isSignedIn)} cookie=${Boolean(hasAccessCookie)} whoamiOk=${Boolean(whoamiOk)}`);
      } catch { /* noop */ }
      prevReadyRef.current = ready;
    }
  }, [clerkEnabled, isSignedIn, hasAccessCookie, whoamiOk]);

  // Single-shot finisher: when signed-in but cookie missing, mint cookies fast and refresh
  const runFinish = useCallback(async () => {
    if (typeof window === 'undefined') return;
    setFinishBusy(true);
    setFinishError(null);
    try {
      try { finishAbortRef.current?.abort(); } catch { /* noop */ }
      const controller = new AbortController();
      finishAbortRef.current = controller;
      const t = setTimeout(() => controller.abort(), 5000);
      const url = new URL('/v1/auth/finish', window.location.origin);
      url.searchParams.set('next', '/');
      console.info('AUTH finisher: POST /v1/auth/finish');
      await fetch(url.toString(), { method: 'POST', redirect: 'follow', credentials: 'include', signal: controller.signal });
      clearTimeout(t);
    } catch (e: any) {
      const msg = e?.name === 'AbortError' ? 'Timed out' : (e?.message || 'failed');
      setFinishError(msg);
    } finally {
      finishAbortRef.current = null;
      setFinishBusy(false);
      setHasAccessCookie(readHasAccessCookie());
      try {
        const r = await fetch('/v1/whoami', { credentials: 'include' });
        if (r.ok) {
          const b: any = await r.json().catch(() => ({}));
          const ok = Boolean(b && (b.is_authenticated || (b.user_id && b.user_id !== 'anon')));
          setWhoamiOk(ok);
          if (ok) setAuthed(true);
        }
      } catch { /* ignore */ }
      try { router.refresh(); } catch { /* noop */ }
    }
  }, [readHasAccessCookie, router]);

  useEffect(() => {
    if (!clerkEnabled) return;
    if (finishOnceRef.current) return;
    if (isSignedIn && !hasAccessCookie) {
      try { console.info('AUTH finisher.trigger reason=cookie.missing'); } catch { }
      finishOnceRef.current = true;
      runFinish();
    }
  }, [clerkEnabled, isSignedIn, hasAccessCookie, runFinish]);
  // Music: initial load + subscribe to hub events
  useEffect(() => {
    (async () => {
      try { setMusicState(await getMusicState()); } catch { }
    })();
    const onState = (ev: Event) => {
      try { const detail = (ev as CustomEvent).detail as MusicState; setMusicState(detail || null); } catch { }
    };
    window.addEventListener('music.state', onState as EventListener);
    return () => { window.removeEventListener('music.state', onState as EventListener); };
  }, []);


  // Check onboarding status when authed
  useEffect(() => {
    const checkOnboarding = async () => {
      if (authed && !authBootOnce.current) {
        try {
          const { getOnboardingStatus } = await import('@/lib/api');
          const status = await getOnboardingStatus();
          if (!status.completed) {
            router.push('/onboarding');
          }
        } catch (error) {
          console.error('Failed to check onboarding status:', error);
          // If there's an error, assume onboarding is needed
          router.push('/onboarding');
        }
        authBootOnce.current = true;
      }
    };

    checkOnboarding();
  }, [authed, router]);

  // React to auth token changes (login/logout in other tabs)
  useEffect(() => {
    const onSet = () => setAuthed(Boolean(getToken()));
    const onClear = () => setAuthed(Boolean(getToken()));
    window.addEventListener('auth:tokens_set', onSet);
    window.addEventListener('auth:tokens_cleared', onClear);
    return () => {
      window.removeEventListener('auth:tokens_set', onSet);
      window.removeEventListener('auth:tokens_cleared', onClear);
    };
  }, []);

  // Persist messages after each update & auto‑scroll
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem(
        historyKey,
        JSON.stringify(messages.filter(m => !m.loading).slice(-100)),
      );
    }
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Persist model selection
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem(modelKey, model);
    }
  }, [model]);

  const handleSend = async (text: string) => {
    if (!text.trim()) return;
    if (!(authed && (sessionReady || !clerkEnabled))) {
      // Prevent sending when unauthenticated
      setMessages(prev => ([
        ...prev,
        { id: crypto.randomUUID(), role: 'assistant', content: 'Please sign in to chat.', loading: false },
      ]));
      return;
    }
    if (!isOnline) {
      setMessages(prev => ([
        ...prev,
        { id: crypto.randomUUID(), role: 'assistant', content: 'You are offline. I will send this when you are back online.', loading: false },
      ]));
      return;
    }

    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: text };
    const assistantId = crypto.randomUUID();
    const placeholder: ChatMessage = { id: assistantId, role: 'assistant', content: '', loading: true };
    setMessages(prev => [
      ...prev,
      userMessage,
      placeholder,
    ]);
    setLoading(true);

    try {
      const full = await sendPrompt(text, model, chunk => {
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId
              ? { ...m, loading: false, content: m.content + chunk }
              : m,
          ),
        );
      });
      // Ensure final content is set even if the backend didn't stream tokens
      if (typeof full === 'string') {
        setMessages(prev =>
          prev.map(m => (m.id === assistantId ? { ...m, loading: false, content: full } : m)),
        );
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantId
            ? { ...m, loading: false, content: `❌ ${message}` }
            : m,
        ),
      );
    } finally {
      setLoading(false);
    }
  };

  const clearHistory = () => {
    setMessages([createInitialMessage()]);
  };

  return (
    (clerkEnabled && !isLoaded) ? (
      <main className="mx-auto max-w-3xl px-4">
        <div className="flex min-h-[calc(100vh-56px)] items-center justify-center text-xs text-muted-foreground">Loading…</div>
      </main>
    ) : (
      <main className="mx-auto max-w-3xl px-4">
        <div className="flex min-h-[calc(100vh-56px)] flex-col">
          {authed && musicState && (
            <section className="py-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="md:col-span-2 space-y-4">
                  <NowPlayingCard state={musicState} />
                  {/* Emphasize Discovery when higher energy */}
                  {musicState.vibe.energy >= 0.5 ? (
                    <DiscoveryCard />
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <DiscoveryCard />
                      <div className="hidden md:block" />
                    </div>
                  )}
                </div>
                <div className="space-y-4">
                  <MoodDial />
                  <QueueCard />
                  <DevicePicker />
                </div>
              </div>
            </section>
          )}
          {/* chat scroll area */}
          <section className="flex-1 overflow-y-auto py-6">
            {clerkEnabled ? (
              <SignedOut>
                <div className="mb-4 rounded-xl border p-4 text-sm bg-card/50">
                  <p className="mb-2">You&apos;re not signed in. Please sign in to enable full features.</p>
                  <div className="flex gap-2">
                    <SignInButton mode="modal">
                      <Button size="sm" variant="secondary">Sign in</Button>
                    </SignInButton>
                    <SignUpButton mode="modal">
                      <Button size="sm">Sign up</Button>
                    </SignUpButton>
                  </div>
                </div>
              </SignedOut>
            ) : (
              !authed && (
                <div className="mb-4 rounded-xl border p-4 text-sm bg-card/50">
                  <p className="mb-2">You&apos;re not signed in. Please sign in to enable full features.</p>
                  <a
                    href="/login"
                    className="inline-flex items-center rounded-md bg-primary px-3 py-1 text-primary-foreground hover:opacity-90"
                  >
                    Go to Login
                  </a>
                </div>
              )
            )}
            {messages.map(m =>
              m.loading ? (
                <LoadingBubble key={m.id} />
              ) : (
                <ChatBubble key={m.id} role={m.role} text={m.content} />
              )
            )}
            <div ref={bottomRef} />
          </section>

          {/* input pinned bottom */}
          <footer className="sticky bottom-0 w-full border-t bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
            <div className="mx-auto max-w-2xl py-4">
              <InputBar
                onSend={handleSend}
                loading={loading}
                model={model}
                onModelChange={setModel}
                authed={authed && (sessionReady || !clerkEnabled)}
              />
              {backendOffline ? (
                <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                  <div>Backend offline — retrying…</div>
                </div>
              ) : (!authed || (clerkEnabled && !sessionReady)) ? (
                <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                  <div>
                    {clerkEnabled ? (sessionReady ? '' : 'Finalizing sign-in…') : (!authed ? 'Sign in required' : '')}
                  </div>
                  {clerkEnabled && isSignedIn && !hasAccessCookie && (
                    <div className="flex items-center gap-3">
                      {finishError ? <span className="text-red-600">{finishError}</span> : null}
                      <button className="underline disabled:opacity-60" disabled={finishBusy} onClick={() => { try { console.info('AUTH finisher.retry reason=manual'); } catch { }; runFinish(); }}>
                        {finishBusy ? 'Retrying…' : 'Retry sign-in'}
                      </button>
                    </div>
                  )}
                </div>
              ) : null}
              <div className="mt-2 flex justify-end">
                <Button
                  onClick={clearHistory}
                  variant="ghost"
                  size="sm"
                  className="text-xs"
                >
                  Clear history
                </Button>
              </div>
            </div>
          </footer>
        </div>
        <RateLimitToast />
      </main>
    )
  );
}
