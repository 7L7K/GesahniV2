// src/components/ChatBubble.tsx
import { cn } from "@/lib/utils"; // if you have a clsx helper
import { Bot, User } from "lucide-react";

export default function ChatBubble({
  role,
  text,
  ghost = false,
}: {
  role: "user" | "assistant";
  text: string;
  ghost?: boolean;
}) {
  const isUser = role === "user";
  return (
    <div className={cn("flex items-start gap-2 mb-3", isUser && "justify-end")}>
      {!isUser && (
        <div className="shrink-0 mt-1 text-muted-foreground">
          <Bot className="size-5" />
        </div>
      )}
      <p
        className={cn(
          "rounded-2xl px-4 py-2 max-w-[75%] text-sm leading-relaxed",
          ghost && "opacity-60 italic",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-card text-card-foreground"
        )}
      >
        {text}
      </p>
      {isUser && (
        <div className="shrink-0 mt-1 text-primary">
          <User className="size-5" />
        </div>
      )}
    </div>
  );
}
