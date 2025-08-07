'use client';

import React, { useState, useRef, useEffect } from 'react';
import ChatBubble from '../components/ChatBubble';
import InputBar from '../components/InputBar';
import { Button } from '@/components/ui/button';
import { sendPrompt } from '@/lib/api';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export default function Page() {
  const initialMessage: ChatMessage = {
    role: 'assistant',
    content: "Hey King, what’s good?",
  };
  const [messages, setMessages] = useState<ChatMessage[]>([initialMessage]);
  const [loading, setLoading] = useState(false);
  const [model, setModel] = useState('llama3');
  const bottomRef = useRef<HTMLDivElement>(null);

  // Hydrate from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem('chat-history');
    if (stored) {
      try {
        setMessages(JSON.parse(stored));
      } catch {
        setMessages([initialMessage]);
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

  const handleSend = async (text: string) => {
    console.log('handleSend invoked');
    if (!text.trim()) return;
    console.log('Outgoing prompt:', text);

    // Optimistically render the user message
    setMessages(prev => [...prev, { role: 'user', content: text }]);
    setLoading(true);

    try {
      // 🔗 Use the shared helper so we always hit NEXT_PUBLIC_API_URL
      const replyText = await sendPrompt(text, model);
      console.log('Response received:', replyText);
      setMessages(prev => [...prev, { role: 'assistant', content: replyText }]);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `❌ ${message}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const clearHistory = () => {
    setMessages([initialMessage]);
  };

  return (
    <main className="flex flex-col h-screen bg-muted/50">
      {/* chat scroll area */}
      <section className="flex-1 overflow-y-auto p-4">
        {messages.map((m, idx) => (
          <ChatBubble key={idx} role={m.role} text={m.content} />
        ))}
        {loading && <ChatBubble role="assistant" text="…" ghost />}
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
