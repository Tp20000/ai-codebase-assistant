/**
 * Card Component
 * AI Codebase Assistant v2.0
 */

import { type ReactNode } from "react";
import { clsx } from "clsx";

interface CardProps {
  children: ReactNode;
  className?: string;
  /** Makes the card clickable with hover effect */
  onClick?: () => void;
  /** Padding preset */
  padding?: "none" | "sm" | "md" | "lg";
}

/**
 * Base card with border and background.
 * Use CardHeader, CardBody, CardFooter for structured content.
 */
export function Card({ children, className, onClick, padding = "md" }: CardProps) {
  const paddings = { none: "", sm: "p-3", md: "p-4", lg: "p-6" };
  return (
    <div
      onClick={onClick}
      className={clsx(
        "rounded-xl border border-[var(--border)]",
        "bg-[var(--bg-secondary)]",
        "transition-colors duration-150",
        onClick && "cursor-pointer hover:border-[var(--border-focus)] hover:bg-[var(--bg-tertiary)]",
        paddings[padding],
        className
      )}
    >
      {children}
    </div>
  );
}

export function CardHeader({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={clsx("flex items-center justify-between mb-3", className)}>
      {children}
    </div>
  );
}

export function CardBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={clsx("", className)}>{children}</div>;
}

export function CardFooter({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={clsx("mt-4 pt-3 border-t border-[var(--border)]", className)}>
      {children}
    </div>
  );
}