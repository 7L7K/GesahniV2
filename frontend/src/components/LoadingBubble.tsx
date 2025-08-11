import { Bot } from "lucide-react";

export default function LoadingBubble() {
  return (
    <div className="flex items-start gap-2 mb-3">
      <div className="shrink-0 mt-1 text-muted-foreground">
        <Bot className="size-5" />
      </div>
      <div className="rounded-2xl px-4 py-2 max-w-[75%] bg-card text-card-foreground shadow-sm">
        <div className="flex items-center gap-2 text-sm">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-t-transparent border-primary" />
          <span>Thinking…</span>
        </div>
      </div>
    </div>
  );
}
