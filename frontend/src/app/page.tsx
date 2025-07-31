'use client';

import React, { useState, useRef, useEffect } from 'react';
import ChatBubble from '../components/ChatBubble';
import InputBar from '../components/InputBar';
import { sendPrompt } from '@/lib/api';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export default function Page() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: 'assistant', content: "Hey King, what’s good?" },
  ]);
  const [loading, setLoading] = useState(false);
  const [model, setModel] = useState('llama3');
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto‑scroll whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (text: string) => {
    if (!text.trim()) return;

    // Optimistically render the user message
    setMessages(prev => [...prev, { role: 'user', content: text }]);
    setLoading(true);

    try {
      // 🔗 Use the shared helper so we always hit NEXT_PUBLIC_API_URL
      const replyText = await sendPrompt(text, model);
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
        <div className="max-w-2xl mx-auto p-4">
          <InputBar
            onSend={handleSend}
            loading={loading}
            model={model}
            onModelChange={setModel}
          />
        </div>
      </footer>
    </main>
  );
}
