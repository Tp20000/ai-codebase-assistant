/**
 * Agent Report Viewer - Step 47
 * AI Codebase Assistant v2.0
 *
 * Renders the markdown report from a completed agent task.
 * Shows: summary stats, code blocks with copy, source citations.
 */

import { useState } from "react";
import { motion } from "framer-motion";
import { clsx } from "clsx";
import type { AgentTaskResult } from "@/services/agentService";
import { getAgentMeta } from "@/services/agentService";

// ── Simple markdown renderer ───────────────────────────────────────

function renderMarkdown(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const codeBlockRegex = /```(\w+)?\n?([\s\S]*?)```/g;
  let last = 0;
  let i = 0;
  let match: RegExpExecArray | null;

  while ((match = codeBlockRegex.exec(text)) !== null) {
    // Text before code block
    if (match.index > last) {
      parts.push(
        <span key={i++} className="whitespace-pre-wrap text-xs text-[var(--text-secondary)]">
          {text.slice(last, match.index)}
        </span>
      );
    }
    // Code block
    const lang = match[1] ?? "";
    const code = match[2].trim();
    parts.push(
      <CodeBlockInReport key={i++} code={code} language={lang} />
    );
    last = match.index + match[0].length;
  }

  // Remaining text
  if (last < text.length) {
    parts.push(
      <span key={i++} className="whitespace-pre-wrap text-xs text-[var(--text-secondary)]">
        {text.slice(last)}
      </span>
    );
  }

  return parts;
}

function CodeBlockInReport({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {}
  };

  return (
    <div className="my-2 rounded-lg border border-[var(--border)] overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 bg-[var(--bg-tertiary)] border-b border-[var(--border)]">
        <span className="text-[10px] text-[var(--text-muted)] uppercase">{language || "code"}</span>
        <button
          onClick={handleCopy}
          className={clsx(
            "text-[10px] px-2 py-0.5 rounded transition-colors",
            copied ? "text-green-400" : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
          )}
        >
          {copied ? "✓ Copied" : "Copy"}
        </button>
      </div>
      <pre className="p-3 overflow-x-auto bg-[var(--bg-primary)] text-xs font-mono text-[var(--text-secondary)]">
        <code>{code}</code>
      </pre>
    </div>
  );
}

// ── Main Report Component ─────────────────────────────────────────

interface AgentReportProps {
  task: AgentTaskResult;
  onClose: () => void;
}

/**
 * Full-screen report viewer for a completed agent task.
 */
export function AgentReport({ task, onClose }: AgentReportProps) {
  const meta = getAgentMeta(task.agent_id);
  const result = task.result as Record<string, unknown> | null;

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      className="h-full flex flex-col bg-[var(--bg-secondary)]"
    >
      {/* Header */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
        <div className="flex items-center gap-2">
          <span className="text-xl">{meta.icon}</span>
          <div>
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {meta.display} Report
            </p>
            {task.elapsed_ms && (
              <p className="text-[10px] text-[var(--text-muted)]">
                Completed in {Math.round(task.elapsed_ms / 1000)}s
              </p>
            )}
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors text-lg"
          aria-label="Close report"
        >
          ×
        </button>
      </div>

      {/* Stats bar */}
      {result && (
        <div className="flex-shrink-0 flex gap-4 px-4 py-2 border-b border-[var(--border)] bg-[var(--bg-tertiary)] overflow-x-auto">
          {Object.entries(result)
            .filter(([k, v]) =>
              typeof v === "number" || typeof v === "string"
            )
            .slice(0, 5)
            .map(([key, val]) => (
              <div key={key} className="flex-shrink-0 text-center">
                <p className="text-[10px] text-[var(--text-muted)] capitalize">
                  {key.replace(/_/g, " ")}
                </p>
                <p className="text-xs font-semibold text-[var(--text-primary)]">
                  {String(val)}
                </p>
              </div>
            ))}
        </div>
      )}

      {/* Report content */}
      <div className="flex-1 overflow-y-auto p-4">
        {task.report ? (
          <div className="prose max-w-none">
            {renderMarkdown(task.report)}
          </div>
        ) : (
          <p className="text-sm text-[var(--text-muted)] italic">
            No report content available.
          </p>
        )}
      </div>

      {/* Actions */}
      <div className="flex-shrink-0 flex gap-2 px-4 py-3 border-t border-[var(--border)]">
        <button
          onClick={async () => {
            if (task.report) {
              await navigator.clipboard.writeText(task.report);
            }
          }}
          className="flex-1 py-1.5 text-xs rounded-lg border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] transition-colors"
        >
          Copy Report
        </button>
        <button
          onClick={onClose}
          className="flex-1 py-1.5 text-xs rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors"
        >
          Back to Agents
        </button>
      </div>
    </motion.div>
  );
}