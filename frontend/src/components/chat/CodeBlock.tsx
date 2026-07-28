/**
 * Code Block Component - Step 45
 * AI Codebase Assistant v2.0
 *
 * Syntax-highlighted code block with one-click copy button.
 */

import { useState } from "react";
import { clsx } from "clsx";

interface CodeBlockProps {
  /** Source code string */
  code: string;
  /** Programming language for syntax highlighting label */
  language?: string;
  /** Show filename header */
  filename?: string;
}

/**
 * Code block with language badge and copy-to-clipboard button.
 *
 * @example
 * <CodeBlock code="def hello(): pass" language="python" />
 */
export function CodeBlock({ code, language = "code", filename }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const ta = document.createElement("textarea");
      ta.value = code;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="rounded-lg overflow-hidden border border-[var(--border)] my-2">
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[var(--bg-tertiary)] border-b border-[var(--border)]">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wide">
            {language}
          </span>
          {filename && (
            <span className="text-[10px] text-[var(--text-muted)]">{filename}</span>
          )}
        </div>
        <button
          onClick={handleCopy}
          className={clsx(
            "text-[10px] px-2 py-0.5 rounded transition-colors",
            copied
              ? "text-green-400 bg-green-500/10"
              : "text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]"
          )}
          aria-label="Copy code"
        >
          {copied ? "✓ Copied" : "Copy"}
        </button>
      </div>

      {/* Code content */}
      <pre className="overflow-x-auto p-3 bg-[var(--bg-primary)] text-xs font-mono text-[var(--text-secondary)] leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  );
}