'use client';

import React, { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import ChatBubble from '../components/ChatBubble';
import LoadingBubble from '../components/LoadingBubble';
import InputBar from '../components/InputBar';
import { Button } from '@/components/ui/button';
import { sendPrompt, getToken, getMusicState, type MusicState, wsUrl } from '@/lib/api';
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

  // Hydrate from localStorage on mount; if none, seed with initial assistant msg
  useEffect(() => {
    if (typeof window !== 'undefined') {
      setAuthed(Boolean(getToken()));
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
  }, []);
  // Music: initial load + live updates via WS
  useEffect(() => {
    let ws: WebSocket | null = null;
    const init = async () => {
      try {
        const st = await getMusicState();
        setMusicState(st);
      } catch { }
      try {
        const url = wsUrl('/v1/ws/music');
        ws = new WebSocket(url);
        ws.onmessage = (ev) => {
          try {
            const msg = JSON.parse(ev.data);
            if (msg?.topic === 'music.state') {
              setMusicState(msg.data as MusicState);
            }
          } catch { }
        };
      } catch { }
    };
    init();
    return () => { try { ws?.close(); } catch { } };
  }, []);


  // Check onboarding status when authed
  useEffect(() => {
    const checkOnboarding = async () => {
      if (authed) {
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
    if (!authed) {
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
          {!authed && (
            <div className="mb-4 rounded-xl border p-4 text-sm bg-card/50">
              <p className="mb-2">
                You&apos;re not signed in. Please sign in to enable full features.
              </p>
              <a
                href="/login"
                className="inline-flex items-center rounded-md bg-primary px-3 py-1 text-primary-foreground hover:opacity-90"
              >
                Go to Login
              </a>
            </div>
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
              authed={authed}
            />
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
  );
}
