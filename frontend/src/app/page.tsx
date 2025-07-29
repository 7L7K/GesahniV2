// src/app/page.tsx
'use client';

import React, { useState, useRef, useEffect } from 'react';
import ChatBubble from '../components/ChatBubble';
import InputBar from '../components/InputBar';

export default function Page() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Hey King, what’s good?' },
  ]);
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  // auto‑scroll on new msgs
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (text: string) => {
    if (!text.trim()) return;
    setMessages(m => [...m, { role: 'user', content: text }]);
    setLoading(true);

    // 🔗 call your API exactly like before
    try {
      const reply = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: text }),
      }).then(r => r.json());
      setMessages(m => [...m, { role: 'assistant', content: reply.response }]);
    } catch (err: any) {
      setMessages(m => [...m, { role: 'assistant', content: `❌ ${err.message}` }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex flex-col h-screen bg-muted/50">
      {/* chat scroll area */}
      <section className="flex-1 overflow-y-auto p-4">
        {messages.map((m, i) => (
          <ChatBubble key={i} role={m.role} text={m.content} />
        ))}
        {loading && <ChatBubble role="assistant" text="..." ghost />}
        <div ref={bottomRef} />
      </section>

      {/* input pinned bottom */}
      <footer className="sticky bottom-0 w-full border-t bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="max-w-2xl mx-auto p-4">
          <InputBar onSend={handleSend} loading={loading} />
        </div>
      </footer>
    </main>
  );
}
