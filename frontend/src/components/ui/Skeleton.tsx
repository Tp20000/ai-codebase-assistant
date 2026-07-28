/**
 * Skeleton Loading Component
 * AI Codebase Assistant v2.0
 */

import { clsx } from "clsx";

interface SkeletonProps {
  className?: string;
  /** Use "text" for text-like lines, "rect" for blocks */
  variant?: "text" | "rect" | "circle";
}

/**
 * Animated skeleton placeholder shown during data loading.
 *
 * @example
 * <Skeleton className="h-4 w-48" />
 * <Skeleton variant="circle" className="w-10 h-10" />
 */
export function Skeleton({ className, variant = "rect" }: SkeletonProps) {
  return (
    <div
      className={clsx(
        "animate-pulse bg-[var(--bg-hover)]",
        variant === "circle" && "rounded-full",
        variant === "text"   && "rounded h-4",
        variant === "rect"   && "rounded-lg",
        className
      )}
      aria-hidden="true"
    />
  );
}

/** Pre-built skeleton for a stat card */
export function StatCardSkeleton() {
  return (
    <div className="p-4 rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)]">
      <Skeleton className="h-3 w-20 mb-3" />
      <Skeleton className="h-8 w-16 mb-1" />
      <Skeleton className="h-3 w-24" />
    </div>
  );
}

/** Pre-built skeleton for a project card */
export function ProjectCardSkeleton() {
  return (
    <div className="p-4 rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)]">
      <div className="flex items-start justify-between mb-3">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-5 w-16 rounded-full" />
      </div>
      <Skeleton variant="text" className="w-full mb-1" />
      <Skeleton variant="text" className="w-3/4 mb-4" />
      <div className="flex gap-3">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-3 w-16" />
      </div>
    </div>
  );
}