/**
 * Agent Task Card - Step 47
 * AI Codebase Assistant v2.0
 *
 * Shows an individual agent task with:
 *   - Animated SVG circular progress ring
 *   - Status badge (QUEUED / RUNNING / COMPLETED / FAILED)
 *   - Current step text
 *   - Elapsed time counter
 *   - View report button when done
 */

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { clsx } from "clsx";
import type { AgentTaskResult } from "@/services/agentService";
import { getAgentMeta } from "@/services/agentService";

// ── Circular Progress Ring ────────────────────────────────────────

interface ProgressRingProps {
  /** 0.0 – 1.0 */
  progress: number;
  /** Ring diameter in px */
  size?: number;
  /** Ring stroke width */
  strokeWidth?: number;
  /** Color of the filled arc */
  color?: string;
  /** Center content */
  children?: React.ReactNode;
}

/**
 * Animated SVG circular progress ring.
 *
 * @example
 * <ProgressRing progress={0.65} color="#3B82F6" size={64}>
 *   <span>65%</span>
 * </ProgressRing>
 */
export function ProgressRing({
  progress,
  size = 64,
  strokeWidth = 5,
  color = "#3B82F6",
  children,
}: ProgressRingProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - Math.min(1, Math.max(0, progress)));

  return (
    <div className="relative flex-shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        {/* Track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--bg-hover)"
          strokeWidth={strokeWidth}
        />
        {/* Progress arc */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        />
      </svg>
      {/* Center label */}
      {children && (
        <div className="absolute inset-0 flex items-center justify-center">
          {children}
        </div>
      )}
    </div>
  );
}

// ── Status Badge ──────────────────────────────────────────────────

const STATUS_CONFIG = {
  QUEUED:    { label: "Queued",    color: "text-[var(--text-muted)]", bg: "bg-[var(--bg-hover)]" },
  PENDING:   { label: "Pending",   color: "text-amber-400",           bg: "bg-amber-500/10" },
  RUNNING:   { label: "Running",   color: "text-blue-400",            bg: "bg-blue-500/10" },
  COMPLETED: { label: "Done",      color: "text-green-400",           bg: "bg-green-500/10" },
  FAILED:    { label: "Failed",    color: "text-red-400",             bg: "bg-red-500/10" },
  CANCELLED: { label: "Cancelled", color: "text-[var(--text-muted)]", bg: "bg-[var(--bg-hover)]" },
} as const;

// ── Agent Task Card ───────────────────────────────────────────────

interface AgentTaskCardProps {
  task: AgentTaskResult;
  onViewReport: (task: AgentTaskResult) => void;
}

/**
 * Card displaying an agent task's progress and status.
 */
export function AgentTaskCard({ task, onViewReport }: AgentTaskCardProps) {
  const meta = getAgentMeta(task.agent_id);
  const [elapsed, setElapsed] = useState(0);
  const cfg = STATUS_CONFIG[task.status] ?? STATUS_CONFIG.QUEUED;
  const pct = Math.round((task.progress ?? 0) * 100);
  const isRunning = task.status === "RUNNING" || task.status === "PENDING";
  const isDone    = task.status === "COMPLETED";
  const isFailed  = task.status === "FAILED";

  // Elapsed time counter
  useEffect(() => {
    if (!isRunning) return;
    const start = Date.now();
    const t = setInterval(() => setElapsed(Date.now() - start), 1000);
    return () => clearInterval(t);
  }, [isRunning]);

  const elapsedStr = elapsed > 0
    ? `${Math.floor(elapsed / 1000)}s`
    : task.elapsed_ms
    ? `${Math.round(task.elapsed_ms / 1000)}s`
    : "";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-start gap-3 p-3 rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)]"
    >
      {/* Progress ring */}
      <ProgressRing
        progress={task.progress ?? 0}
        color={isFailed ? "#EF4444" : isDone ? "#10B981" : meta.color}
        size={56}
        strokeWidth={4}
      >
        <span className="text-xl">{meta.icon}</span>
      </ProgressRing>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2 mb-1">
          <p className="text-sm font-medium text-[var(--text-primary)] truncate">
            {meta.display}
          </p>
          <span className={clsx("text-[10px] px-1.5 py-0.5 rounded font-medium flex-shrink-0", cfg.bg, cfg.color)}>
            {cfg.label}
          </span>
        </div>

        {/* Progress bar */}
        <div className="h-1 bg-[var(--bg-hover)] rounded-full overflow-hidden mb-1.5">
          <motion.div
            className="h-full rounded-full"
            style={{ backgroundColor: isFailed ? "#EF4444" : isDone ? "#10B981" : meta.color }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.4 }}
          />
        </div>

        {/* Step + timing */}
        <div className="flex items-center justify-between">
          <p className="text-[10px] text-[var(--text-muted)] truncate">
            {isFailed
              ? task.error?.slice(0, 60) ?? "Failed"
              : task.current_step ?? meta.description}
          </p>
          <span className="text-[10px] text-[var(--text-muted)] flex-shrink-0 ml-2">
            {pct}%{elapsedStr ? ` · ${elapsedStr}` : ""}
          </span>
        </div>

        {/* View report button */}
        {isDone && task.report && (
          <button
            onClick={() => onViewReport(task)}
            className="mt-2 text-[10px] px-2 py-1 rounded bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 border border-blue-500/20 transition-colors"
          >
            View Report →
          </button>
        )}

        {/* Spinning indicator */}
        {isRunning && (
          <div className="mt-1.5 flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-full border border-blue-500 border-t-transparent animate-spin" />
            <span className="text-[10px] text-blue-400">Processing...</span>
          </div>
        )}
      </div>
    </motion.div>
  );
}