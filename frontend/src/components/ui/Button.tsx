/**
 * Reusable Button Component
 * AI Codebase Assistant v2.0
 */

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { clsx } from "clsx";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize    = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Visual style variant */
  variant?: ButtonVariant;
  /** Size preset */
  size?: ButtonSize;
  /** Show loading spinner and disable interactions */
  isLoading?: boolean;
  /** Icon shown before label */
  leftIcon?: ReactNode;
  /** Icon shown after label */
  rightIcon?: ReactNode;
  /** Stretch to full container width */
  fullWidth?: boolean;
}

/**
 * Button with multiple variants, sizes, and a loading state.
 *
 * @example
 * <Button variant="primary" isLoading={isPending}>Sign In</Button>
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = "primary",
      size = "md",
      isLoading = false,
      leftIcon,
      rightIcon,
      fullWidth = false,
      className,
      disabled,
      children,
      ...props
    },
    ref
  ) => {
    const base =
      "inline-flex items-center justify-center gap-2 font-medium rounded-lg " +
      "transition-all duration-150 focus-visible:outline-none " +
      "focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 " +
      "focus-visible:ring-offset-[var(--bg-primary)] " +
      "disabled:opacity-50 disabled:cursor-not-allowed select-none";

    const variants: Record<ButtonVariant, string> = {
      primary:
        "bg-gradient-to-r from-blue-500 to-purple-600 text-white " +
        "hover:from-blue-600 hover:to-purple-700 active:scale-[0.98] shadow-lg " +
        "shadow-blue-500/20",
      secondary:
        "bg-[var(--bg-tertiary)] text-[var(--text-primary)] " +
        "border border-[var(--border)] " +
        "hover:bg-[var(--bg-hover)] hover:border-[var(--border-focus)] active:scale-[0.98]",
      ghost:
        "text-[var(--text-secondary)] hover:text-[var(--text-primary)] " +
        "hover:bg-[var(--bg-hover)] active:scale-[0.98]",
      danger:
        "bg-red-500/10 text-red-400 border border-red-500/30 " +
        "hover:bg-red-500/20 hover:border-red-500/50 active:scale-[0.98]",
    };

    const sizes: Record<ButtonSize, string> = {
      sm: "px-3 py-1.5 text-xs h-8",
      md: "px-4 py-2   text-sm h-9",
      lg: "px-6 py-2.5 text-sm h-11",
    };

    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={clsx(
          base,
          variants[variant],
          sizes[size],
          fullWidth && "w-full",
          className
        )}
        {...props}
      >
        {isLoading ? (
          <>
            <Spinner />
            <span>Loading...</span>
          </>
        ) : (
          <>
            {leftIcon}
            {children}
            {rightIcon}
          </>
        )}
      </button>
    );
  }
);
Button.displayName = "Button";

/** Small inline spinner */
function Spinner() {
  return (
    <svg
      className="animate-spin h-4 w-4"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12" cy="12" r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}
