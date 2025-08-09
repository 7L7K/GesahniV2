'use client';

import React, { useState, useRef, useEffect } from 'react';
import ChatBubble from '../components/ChatBubble';
import LoadingBubble from '../components/LoadingBubble';
import InputBar from '../components/InputBar';
import { Button } from '@/components/ui/button';
import { sendPrompt, getToken } from '@/lib/api';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  loading?: boolean;
}

export default function Page() {
  const [authed, setAuthed] = useState<boolean>(false);
  const createInitialMessage = (): ChatMessage => ({
    id: crypto.randomUUID(),
    role: 'assistant',
    content: "Hey King, what’s good?",
  });

  const [messages, setMessages] = useState<ChatMessage[]>([
    createInitialMessage(),
  ]);
  const [loading, setLoading] = useState(false);
  const [model, setModel] = useState('gpt-4o');
  const bottomRef = useRef<HTMLDivElement>(null);

  // Hydrate from localStorage on mount
  useEffect(() => {
    if (typeof window !== 'undefined') {
      setAuthed(Boolean(getToken()));
      const stored = localStorage.getItem('chat-history');
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
            setMessages(validMessages);
          } else {
            setMessages([createInitialMessage()]);
          }
        } catch {
          setMessages([createInitialMessage()]);
        }
      }

      // Also hydrate the model selection
      const storedModel = localStorage.getItem('selected-model');
      if (storedModel) {
        setModel(storedModel);
      }
    }
  }, []);

  // Persist messages after each update & auto‑scroll
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem(
        'chat-history',
        JSON.stringify(messages.filter(m => !m.loading).slice(-100)),
      );
    }
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Persist model selection
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('selected-model', model);
    }
  }, [model]);

  const handleSend = async (text: string) => {
    if (!text.trim()) return;

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
    <main className="mx-auto h-[calc(100vh-56px)] max-w-3xl px-4">
      <div className="flex h-full flex-col">
        {/* chat scroll area */}
        <section className="flex-1 overflow-y-auto py-4">
          {!authed && (
            <div className="mb-4 rounded-lg border p-4 text-sm">
              <p className="mb-2">You&apos;re not signed in. Please sign in to enable full features.</p>
              <a
                href="/login"
                className="inline-flex items-center rounded bg-primary px-3 py-1 text-primary-foreground hover:opacity-90"
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
    </main>
  );
}
