import React from 'react';

export interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface ChatProps {
  messages: Message[];
}

const Chat: React.FC<ChatProps> = ({ messages }) => {
  return (
    <div className="space-y-2">
      {messages.map((m, i) => (
        <div key={i} className={m.role === 'user' ? 'text-right' : 'text-left'}>
          <span className={
            m.role === 'user'
              ? 'bg-blue-500 text-white rounded px-2 py-1'
              : 'bg-gray-200 rounded px-2 py-1'
          }>
            {m.content}
          </span>
        </div>
      ))}
    </div>
  );
};

export default Chat;
