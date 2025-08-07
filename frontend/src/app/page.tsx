'use client';

import React, { useState, useRef, useEffect } from 'react';
import ChatBubble from '../components/ChatBubble';
import InputBar from '../components/InputBar';
import { Button } from '@/components/ui/button';
import { sendPrompt } from '@/lib/api';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

export default function Page() {
  const createInitialMessage = (): ChatMessage => ({
    id: crypto.randomUUID(),
    role: 'assistant',
    content: "Hey King, what’s good?",
  });

  const [messages, setMessages] = useState<ChatMessage[]>([
    createInitialMessage(),
  ]);
  const [loading, setLoading] = useState(false);
  const [model, setModel] = useState(() =>
    localStorage.getItem('selected-model') || 'llama3'
  );
  const bottomRef = useRef<HTMLDivElement>(null);

  // Hydrate from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem('chat-history');
    if (stored) {
      try {
        const parsed: ChatMessage[] = JSON.parse(stored);
        setMessages(
          parsed.map(m => ({ ...m, id: m.id ?? crypto.randomUUID() })),
        );
      } catch {
        setMessages([createInitialMessage()]);
      }
    }
  }, []);

  // Persist messages after each update & auto‑scroll
  useEffect(() => {
    localStorage.setItem(
      'chat-history',
      JSON.stringify(messages.slice(-100)),
    );
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Persist model selection
  useEffect(() => {
    localStorage.setItem('selected-model', model);
  }, [model]);

  const handleSend = async (text: string) => {
    if (!text.trim()) return;

    const userMessage = { id: crypto.randomUUID(), role: 'user', content: text };
    const assistantId = crypto.randomUUID();
    setMessages(prev => [
      ...prev,
      userMessage,
      { id: assistantId, role: 'assistant', content: '…' },
    ]);
    setLoading(true);

    try {
      await sendPrompt(text, model, chunk => {
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId
              ? { ...m, content: (m.content === '…' ? '' : m.content) + chunk }
              : m,
          ),
        );
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantId
            ? { ...m, content: `❌ ${message}` }
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
    <main className="flex flex-col h-screen bg-muted/50">
      {/* chat scroll area */}
      <section className="flex-1 overflow-y-auto p-4">
        {messages.map(m => (
          <ChatBubble key={m.id} role={m.role} text={m.content} />
        ))}
        <div ref={bottomRef} />
      </section>

      {/* input pinned bottom */}
      <footer className="sticky bottom-0 w-full border-t bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="max-w-2xl mx-auto p-4 space-y-2">
          <InputBar
            onSend={handleSend}
            loading={loading}
            model={model}
            onModelChange={setModel}
          />
          <Button
            onClick={clearHistory}
            variant="ghost"
            size="sm"
            className="text-xs"
          >
            Clear history
          </Button>
        </div>
      </footer>
    </main>
  );
}
