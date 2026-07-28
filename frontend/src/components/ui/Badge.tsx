/**
 * Badge Component
 * AI Codebase Assistant v2.0
 */

import { clsx } from "clsx";

type BadgeVariant = "default" | "success" | "warning" | "danger" | "info" | "purple";

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  className?: string;
  dot?: boolean;
}

/**
 * Small status badge with color variants.
 */
export function Badge({ children, variant = "default", className, dot = false }: BadgeProps) {
  const variants: Record<BadgeVariant, string> = {
    default: "bg-[var(--bg-hover)] text-[var(--text-secondary)]",
    success: "bg-green-500/10 text-green-400 border border-green-500/20",
    warning: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
    danger:  "bg-red-500/10   text-red-400   border border-red-500/20",
    info:    "bg-blue-500/10  text-blue-400  border border-blue-500/20",
    purple:  "bg-purple-500/10 text-purple-400 border border-purple-500/20",
  };
  const dotColors: Record<BadgeVariant, string> = {
    default: "bg-[var(--text-muted)]",
    success: "bg-green-400",
    warning: "bg-amber-400",
    danger:  "bg-red-400",
    info:    "bg-blue-400",
    purple:  "bg-purple-400",
  };

  return (
    <span className={clsx(
      "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium",
      variants[variant],
      className
    )}>
      {dot && (
        <span className={clsx("w-1.5 h-1.5 rounded-full", dotColors[variant])} />
      )}
      {children}
    </span>
  );
}