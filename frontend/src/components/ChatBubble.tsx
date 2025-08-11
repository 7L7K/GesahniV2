// src/components/ChatBubble.tsx
import { cn } from "@/lib/utils";
import { Bot, User } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import React, { useMemo } from "react";

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
  // Extract sources block and build id -> snippet map for hover tooltips
  const idToSnippet = useMemo(() => {
    const map: Record<string, string> = {};
    const m = text.match(/```sources\n([\s\S]*?)```/i);
    if (m) {
      const body = m[1] || "";
      body.split(/\r?\n/).forEach((line) => {
        const mm = line.match(/^\s*-\s*\(([a-f0-9]{6,})\)\s*(.+)$/i);
        if (mm) {
          const [, id, snippet] = mm;
          map[id] = snippet.trim().slice(0, 200);
        }
      });
    }
    return map;
  }, [text]);

  const enhanced = useMemo(() => {
    const escape = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    return text.replace(/\[#chunk:([a-f0-9]{6,})\]/gi, (_m, id: string) => {
      const tip = idToSnippet[id] || `Source chunk ${id}`;
      return `<span title="${escape(tip)}">[#chunk:${id}]</span>`;
    });
  }, [text, idToSnippet]);

  const display = useMemo(() => {
    // Remove the sources block from display; it's only used for tooltips
    return enhanced.replace(/```sources[\s\S]*?```/gi, "").trim();
  }, [enhanced]);
  return (
    <div className={cn("flex items-start gap-2 mb-3", isUser && "justify-end")}>
      {!isUser && (
        <div className="shrink-0 mt-1 text-muted-foreground">
          <Bot className="size-5" />
        </div>
      )}
      <div
        className={cn(
          "rounded-2xl px-4 py-2 max-w-[75%] text-sm leading-relaxed prose prose-sm dark:prose-invert prose-pre:bg-muted/70 prose-pre:text-foreground shadow-sm",
          ghost && "opacity-60 italic",
          isUser
            ? "bg-primary text-primary-foreground prose-invert"
            : "bg-card text-card-foreground"
        )}
      >
        {isUser ? (
          <p className="m-0 whitespace-pre-wrap">{text}</p>
        ) : (
          <div className="prose prose-sm dark:prose-invert">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
              {display}
            </ReactMarkdown>
          </div>
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
