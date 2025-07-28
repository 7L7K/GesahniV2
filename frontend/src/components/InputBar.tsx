import React, { useState } from 'react';

interface InputBarProps {
  onSend: (text: string) => void;
  disabled?: boolean;
}

const InputBar: React.FC<InputBarProps> = ({ onSend, disabled }) => {
  const [value, setValue] = useState('');

  const send = () => {
    const text = value.trim();
    if (!text) return;
    onSend(text);
    setValue('');
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      send();
    }
  };

  return (
    <div className="flex space-x-2 mt-4">
      <input
        className="flex-grow border rounded px-2 py-1"
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={disabled}
      />
      <button
        className="px-4 py-1 bg-blue-600 text-white rounded"
        onClick={send}
        disabled={disabled}
      >
        Send
      </button>
    </div>
  );
};

export default InputBar;
