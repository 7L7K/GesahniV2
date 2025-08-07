// src/components/InputBar.tsx
import { Send } from "lucide-react";
import { useState, KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export default function InputBar({
  onSend,
  loading,
  model,
  onModelChange,
}: {
  onSend: (text: string) => Promise<void> | void;
  loading: boolean;
  model: string;
  onModelChange: (m: string) => void;
}) {
  const [text, setText] = useState("");

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  const send = async () => {
    const trimmed = text.trim();
    if (!trimmed) return;

    try {
      await onSend(trimmed);
      setText("");
    } catch (err) {
      // Keep input if send fails
      console.error(err);
    }
  };

  return (
    <div className="flex gap-2 items-end">
      <select
        value={model}
        onChange={(e) => onModelChange(e.target.value)}
        className="border border-input rounded-md px-2 py-1 text-sm bg-background"
      >
        <option value="llama3">llama3</option>
        <option value="gpt-4o">gpt-4o</option>
      </select>
      <Textarea
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={handleKey}
        placeholder="Type a message…"
        className="flex-1 resize-none"
        rows={1}
        disabled={loading}
      />
      <Button onClick={() => { void send(); }} disabled={loading || !text.trim()} size="icon">
        <Send className="size-4" />
      </Button>
    </div>
  );
}
