// src/components/InputBar.tsx
import { Send } from "lucide-react";
import { useState, KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import TextareaAutosize from "react-textarea-autosize";

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
    <div className="flex flex-col gap-2">
      <div className="inline-flex w-full items-center justify-between rounded-lg border bg-background p-1">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => onModelChange('auto')}
            className={
              model === 'auto'
                ? 'rounded-md px-3 py-1.5 text-xs bg-primary text-primary-foreground'
                : 'rounded-md px-3 py-1.5 text-xs hover:bg-accent'
            }
          >
            auto
          </button>
          <button
            type="button"
            onClick={() => onModelChange('llama3')}
            className={
              model === 'llama3'
                ? 'rounded-md px-3 py-1.5 text-xs bg-primary text-primary-foreground'
                : 'rounded-md px-3 py-1.5 text-xs hover:bg-accent'
            }
          >
            llama3
          </button>
          <button
            type="button"
            onClick={() => onModelChange('gpt-4o')}
            className={
              model === 'gpt-4o'
                ? 'rounded-md px-3 py-1.5 text-xs bg-primary text-primary-foreground'
                : 'rounded-md px-3 py-1.5 text-xs hover:bg-accent'
            }
          >
            gpt-4o
          </button>
        </div>
        <div className="text-[10px] text-muted-foreground px-2">Shift+Enter for newline</div>
      </div>

      <div className="flex items-end gap-2">
        <div className="flex-1">
          <TextareaAutosize
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Type a message…"
            className="w-full min-h-[40px] max-h-40 resize-none rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            minRows={1}
            maxRows={8}
            disabled={loading}
          />
        </div>
        <Button onClick={() => { void send(); }} disabled={loading || !text.trim()} size="icon">
          <Send className="size-4" />
        </Button>
      </div>
    </div>
  );
}
