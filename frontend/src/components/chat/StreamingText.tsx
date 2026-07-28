/**
 * Streaming Text Component - Step 45
 * AI Codebase Assistant v2.0
 *
 * Renders text with a blinking cursor at the end during streaming.
 */

import { useEffect, useState } from "react";

interface StreamingTextProps {
  /** Text content to display */
  text: string;
  /** Whether streaming is in progress (shows cursor) */
  isStreaming: boolean;
  /** CSS class for the container */
  className?: string;
}

/**
 * Text display with animated cursor while AI is generating.
 *
 * @example
 * <StreamingText text={aiResponse} isStreaming={isLoading} />
 */
export function StreamingText({ text, isStreaming, className }: StreamingTextProps) {
  const [showCursor, setShowCursor] = useState(true);

  // Blink cursor at 530ms interval
  useEffect(() => {
    if (!isStreaming) {
      setShowCursor(false);
      return;
    }
    const interval = setInterval(() => {
      setShowCursor((v) => !v);
    }, 530);
    return () => clearInterval(interval);
  }, [isStreaming]);

  return (
    <span className={className}>
      {text}
      {isStreaming && (
        <span
          className="inline-block w-0.5 h-4 bg-blue-400 ml-0.5 align-middle"
          style={{ opacity: showCursor ? 1 : 0, transition: "opacity 0.1s" }}
          aria-hidden="true"
        />
      )}
    </span>
  );
}