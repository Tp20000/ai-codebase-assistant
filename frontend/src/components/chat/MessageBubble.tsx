/**
 * Message Bubble Component - Step 45
 * AI Codebase Assistant v2.0
 *
 * Renders a single chat message with:
 *   - User messages: right-aligned, blue background
 *   - AI messages: left-aligned, dark background with markdown
 *   - Code blocks with syntax highlighting and copy button
 *   - Source citations when RAG provides context
 */

import { useMemo } from "react";
import { clsx } from "clsx";
import { StreamingText } from "@/components/chat/StreamingText";
import { CodeBlock } from "@/components/chat/CodeBlock";
import type { ChatMessage } from "@/services/chatService";
import { formatMessageTime } from "@/services/chatService";

interface MessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
}

/**
 * Parse markdown-like content into React elements.
 * Handles: code blocks, inline code, bold, and plain text.
 * A full markdown library (react-markdown) can replace this in production.
 */
function parseContent(content: string, isStreaming: boolean): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const codeBlockRegex = /```(\w+)?\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let keyIndex = 0;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    // Text before code block
    if (match.index > lastIndex) {
      const textBefore = content.slice(lastIndex, match.index);
      parts.push(
        <span key={`text-${keyIndex++}`} className="whitespace-pre-wrap">
          {renderInlineMarkdown(textBefore)}
        </span>
      );
    }

    // Code block
    const lang = match[1] || "code";
    const code = match[2].trim();
    parts.push(
      <CodeBlock key={`code-${keyIndex++}`} code={code} language={lang} />
    );

    lastIndex = match.index + match[0].length;
  }

  // Remaining text after last code block
  if (lastIndex < content.length) {
    const remaining = content.slice(lastIndex);
    if (isStreaming) {
      parts.push(
        <StreamingText
          key={`stream-${keyIndex++}`}
          text={remaining}
          isStreaming={isStreaming}
          className="whitespace-pre-wrap"
        />
      );
    } else {
      parts.push(
        <span key={`text-${keyIndex++}`} className="whitespace-pre-wrap">
          {renderInlineMarkdown(remaining)}
        </span>
      );
    }
  }

  // If no parts created (empty content during streaming)
  if (parts.length === 0 && isStreaming) {
    parts.push(
      <StreamingText
        key="stream-empty"
        text=""
        isStreaming={isStreaming}
      />
    );
  }

  return parts;
}

/** Render inline markdown: **bold**, `code`, and plain text */
function renderInlineMarkdown(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  // Split on **bold** and `inline code`
  const regex = /\*\*(.*?)\*\*|`([^`]+)`/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let i = 0;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(<span key={i++}>{text.slice(last, match.index)}</span>);
    }
    if (match[1] !== undefined) {
      parts.push(<strong key={i++} className="font-semibold text-[var(--text-primary)]">{match[1]}</strong>);
    } else if (match[2] !== undefined) {
      parts.push(
        <code key={i++} className="px-1 py-0.5 rounded text-[11px] bg-[var(--bg-tertiary)] border border-[var(--border)] text-green-400 font-mono">
          {match[2]}
        </code>
      );
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    parts.push(<span key={i++}>{text.slice(last)}</span>);
  }
  return parts;
}

/**
 * Individual chat message bubble.
 *
 * @param message     ChatMessage object to display
 * @param isStreaming Whether this message is currently being streamed
 */
export function MessageBubble({ message, isStreaming = false }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";
  const time = formatMessageTime(message.created_at);

  const contentParts = useMemo(
    () => parseContent(message.content, isStreaming),
    [message.content, isStreaming]
  );

  if (isSystem) return null;

  return (
    <div
      className={clsx(
        "flex gap-2 group",
        isUser ? "flex-row-reverse" : "flex-row"
      )}
    >
      {/* Avatar */}
      <div className={clsx(
        "flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold",
        isUser
          ? "bg-gradient-to-br from-blue-500 to-purple-600 text-white"
          : "bg-[var(--bg-tertiary)] border border-[var(--border)] text-[var(--text-muted)]"
      )}>
        {isUser ? "U" : "AI"}
      </div>

      {/* Bubble */}
      <div className={clsx(
        "max-w-[85%] flex flex-col gap-1",
        isUser ? "items-end" : "items-start"
      )}>
        <div className={clsx(
          "rounded-2xl px-3 py-2 text-sm leading-relaxed",
          isUser
            ? "bg-blue-500 text-white rounded-tr-sm"
            : "bg-[var(--bg-tertiary)] border border-[var(--border)] text-[var(--text-primary)] rounded-tl-sm"
        )}>
          {contentParts}
        </div>

        {/* Sources */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-0.5">
            {message.sources.slice(0, 4).map((src, i) => (
              <span
                key={i}
                className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-hover)] text-[var(--text-muted)] border border-[var(--border)] truncate max-w-[160px]"
                title={src.file_path}
              >
                📄 {src.file_path.split("/").pop()}
              </span>
            ))}
          </div>
        )}

        {/* Timestamp */}
        {time && (
          <span className="text-[10px] text-[var(--text-muted)] opacity-0 group-hover:opacity-100 transition-opacity px-1">
            {time}
          </span>
        )}
      </div>
    </div>
  );
}