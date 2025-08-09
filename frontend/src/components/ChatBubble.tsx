// src/components/ChatBubble.tsx
import { cn } from "@/lib/utils";
import { Bot, User } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

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
      <div
        className={cn(
          "rounded-2xl px-4 py-2 max-w-[75%] text-sm leading-relaxed prose prose-sm dark:prose-invert prose-pre:bg-muted/70 prose-pre:text-foreground",
          ghost && "opacity-60 italic",
          isUser
            ? "bg-primary text-primary-foreground prose-invert"
            : "bg-card text-card-foreground"
        )}
      >
        {isUser ? (
          <p className="m-0 whitespace-pre-wrap">{text}</p>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        )}
      </div>
      {isUser && (
        <div className="shrink-0 mt-1 text-primary">
          <User className="size-5" />
        </div>
      )}
    </div>
  );
}
