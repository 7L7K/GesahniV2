// src/components/ChatBubble.tsx
import { cn } from "@/lib/utils";
import { Bot, User } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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

  const display = useMemo(() => {
    // Remove the sources block from display; it's only used for tooltips
    return text.replace(/```sources[\s\S]*?```/gi, "").trim();
  }, [text]);

  function renderAssistantContent() {
    // Render markdown but replace [#chunk:ID] tokens with <span title="..."> elements without using rehypeRaw
    const parts: React.ReactNode[] = [];
    const regex = /\[#chunk:([a-f0-9]{6,})\]/gi;
    let lastIndex = 0;
    let idx = 0;
    let match: RegExpExecArray | null;
    while ((match = regex.exec(display)) !== null) {
      const before = display.slice(lastIndex, match.index);
      if (before) {
        parts.push(
          <ReactMarkdown key={`md-${idx}`} remarkPlugins={[remarkGfm]}>
            {before}
          </ReactMarkdown>
        );
      }
      const id = match[1];
      const tip = idToSnippet[id] || `Source chunk ${id}`;
      parts.push(
        <span key={`chunk-${idx}`} title={tip}>[#chunk:{id}]</span>
      );
      lastIndex = regex.lastIndex;
      idx += 1;
    }
    const after = display.slice(lastIndex);
    if (after) {
      parts.push(
        <ReactMarkdown key={`md-end`} remarkPlugins={[remarkGfm]}>
          {after}
        </ReactMarkdown>
      );
    }
    // If no matches, parts may be empty; render full markdown once
    if (parts.length === 0) {
      return (
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {display}
        </ReactMarkdown>
      );
    }
    return parts;
  }
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
            {renderAssistantContent()}
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
