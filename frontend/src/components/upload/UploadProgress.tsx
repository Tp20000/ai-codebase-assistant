/**
 * Upload Progress Component - Step 44
 * AI Codebase Assistant v2.0
 */

import { motion } from "framer-motion";
import { clsx } from "clsx";
import type { UploadProgress } from "@/services/uploadService";

interface UploadProgressBarProps {
  progress: UploadProgress;
  className?: string;
}

/**
 * Animated progress bar for file upload status.
 *
 * Shows: filename, percentage, status label, and animated fill bar.
 * Status colors: blue=uploading, amber=processing, green=done, red=error
 */
export function UploadProgressBar({ progress, className }: UploadProgressBarProps) {
  const { percentage, fileName, status, loaded, total } = progress;

  const statusConfig = {
    uploading:  { color: "bg-blue-500",  label: "Uploading...",  text: "text-blue-400" },
    processing: { color: "bg-amber-500", label: "Processing...", text: "text-amber-400" },
    done:       { color: "bg-green-500", label: "Complete",      text: "text-green-400" },
    error:      { color: "bg-red-500",   label: "Failed",        text: "text-red-400" },
  };

  const config = statusConfig[status];

  const formatBytes = (b: number) =>
    b > 1024 * 1024
      ? `${(b / 1024 / 1024).toFixed(1)}MB`
      : `${(b / 1024).toFixed(0)}KB`;

  return (
    <div className={clsx("space-y-1.5", className)}>
      {/* Filename + status */}
      <div className="flex items-center justify-between text-xs">
        <span className="text-[var(--text-secondary)] truncate max-w-[200px]">
          {fileName}
        </span>
        <span className={clsx("font-medium flex-shrink-0 ml-2", config.text)}>
          {status === "uploading" || status === "processing"
            ? `${percentage}%`
            : config.label}
        </span>
      </div>

      {/* Progress bar track */}
      <div className="h-1.5 bg-[var(--bg-hover)] rounded-full overflow-hidden">
        <motion.div
          className={clsx("h-full rounded-full", config.color)}
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 0.3, ease: "easeOut" }}
        />
      </div>

      {/* Byte count */}
      {(status === "uploading" || status === "processing") && total > 0 && (
        <p className="text-[10px] text-[var(--text-muted)]">
          {formatBytes(loaded)} / {formatBytes(total)}
        </p>
      )}
    </div>
  );
}

interface MultiFileProgressProps {
  progresses: UploadProgress[];
  className?: string;
}

/**
 * Stack of progress bars for multiple file uploads.
 */
export function MultiFileProgress({ progresses, className }: MultiFileProgressProps) {
  if (progresses.length === 0) return null;

  const doneCount = progresses.filter((p) => p.status === "done").length;
  const totalCount = progresses.length;
  const overallPct = Math.round((doneCount / totalCount) * 100);

  return (
    <div className={clsx("space-y-3", className)}>
      {/* Overall progress */}
      {totalCount > 1 && (
        <div className="pb-2 border-b border-[var(--border)]">
          <div className="flex justify-between text-xs mb-1">
            <span className="text-[var(--text-secondary)]">
              Overall: {doneCount}/{totalCount} files
            </span>
            <span className="text-blue-400">{overallPct}%</span>
          </div>
          <div className="h-1.5 bg-[var(--bg-hover)] rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-blue-500 rounded-full"
              animate={{ width: `${overallPct}%` }}
              transition={{ duration: 0.3 }}
            />
          </div>
        </div>
      )}

      {/* Individual file progress bars */}
      {progresses.map((p, i) => (
        <UploadProgressBar key={i} progress={p} />
      ))}
    </div>
  );
}