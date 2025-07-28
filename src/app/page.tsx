'use client';

import React, { useState } from 'react';
import Chat, { Message } from '../components/Chat';
import InputBar from '../components/InputBar';
import { sendPrompt } from '../lib/api';

export default function Page() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);

  const handleSend = async (text: string) => {
    const userMessage: Message = { role: 'user', content: text };
    setMessages(msgs => [...msgs, userMessage]);
    setLoading(true);
    try {
      const reply = await sendPrompt(text);
      const aiMessage: Message = { role: 'assistant', content: reply };
      setMessages(msgs => [...msgs, aiMessage]);
    } catch (err: any) {
      setMessages(msgs => [...msgs, { role: 'assistant', content: `Error: ${err.message}` }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="max-w-2xl mx-auto p-4">
      <Chat messages={messages} />
      <InputBar onSend={handleSend} disabled={loading} />
    </main>
  );
}
