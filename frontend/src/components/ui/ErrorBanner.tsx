/**
 * Error Banner Component
 * AI Codebase Assistant v2.0
 *
 * Displays a visible, accessible error message.
 * ALL errors must be visible in the UI — never only in console.
 */

import { type ReactNode } from "react";
import { clsx } from "clsx";

interface ErrorBannerProps {
  /** Error message or node to display */
  message: string | ReactNode | null | undefined;
  /** Optional title above the message */
  title?: string;
  /** Additional CSS classes */
  className?: string;
  /** Callback when user dismisses the error */
  onDismiss?: () => void;
}

/**
 * ErrorBanner displays API or validation errors prominently.
 * Renders nothing when message is falsy.
 *
 * @example
 * <ErrorBanner
 *   title="Sign in failed"
 *   message={authStore.error}
 *   onDismiss={authStore.clearError}
 * />
 */
export function ErrorBanner({
  message,
  title,
  className,
  onDismiss,
}: ErrorBannerProps) {
  if (!message) return null;

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={clsx(
        "flex items-start gap-3 p-3 rounded-lg",
        "bg-red-500/10 border border-red-500/30",
        "animate-fade-in",
        className
      )}
    >
      {/* Icon */}
      <div className="flex-shrink-0 mt-0.5 text-red-400" aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {title && (
          <p className="text-sm font-semibold text-red-400 mb-0.5">{title}</p>
        )}
        <p className="text-sm text-red-300 break-words">
          {message}
        </p>
      </div>

      {/* Dismiss button */}
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="
            flex-shrink-0 text-red-400/60
            hover:text-red-400 transition-colors
            focus-visible:outline-none focus-visible:ring-1
            focus-visible:ring-red-500 rounded
          "
          aria-label="Dismiss error"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      )}
    </div>
  );
}
