/**
 * Reusable Input Component
 * AI Codebase Assistant v2.0
 */

import {
  forwardRef,
  useState,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";
import { clsx } from "clsx";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  /** Field label displayed above the input */
  label?: string;
  /** Error message displayed below the input */
  error?: string;
  /** Helper text displayed below the input (when no error) */
  hint?: string;
  /** Icon or element displayed on the left side */
  leftAddon?: ReactNode;
  /** Icon or element displayed on the right side */
  rightAddon?: ReactNode;
  /** Stretch to full container width (default: true) */
  fullWidth?: boolean;
}

/**
 * Input field with label, error state, and icon addons.
 *
 * Integrates with React Hook Form via forwardRef.
 *
 * @example
 * <Input
 *   label="Email"
 *   type="email"
 *   error={errors.email?.message}
 *   {...register("email")}
 * />
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      error,
      hint,
      leftAddon,
      rightAddon,
      fullWidth = true,
      className,
      type,
      id,
      ...props
    },
    ref
  ) => {
    const [showPassword, setShowPassword] = useState(false);
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");
    const isPassword = type === "password";
    const resolvedType = isPassword
      ? showPassword ? "text" : "password"
      : type;

    return (
      <div className={clsx("flex flex-col gap-1.5", fullWidth && "w-full")}>
        {/* Label */}
        {label && (
          <label
            htmlFor={inputId}
            className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wide"
          >
            {label}
          </label>
        )}

        {/* Input wrapper */}
        <div className="relative flex items-center">
          {/* Left addon */}
          {leftAddon && (
            <div className="
              absolute left-3 flex items-center
              text-[var(--text-muted)] pointer-events-none
            ">
              {leftAddon}
            </div>
          )}

          {/* Input element */}
          <input
            ref={ref}
            id={inputId}
            type={resolvedType}
            className={clsx(
              "w-full rounded-lg text-sm transition-colors duration-150",
              "bg-[var(--bg-tertiary)] text-[var(--text-primary)]",
              "border placeholder:text-[var(--text-muted)]",
              "focus:outline-none focus:ring-2 focus:ring-blue-500/50",
              error
                ? "border-red-500/50 focus:border-red-500"
                : "border-[var(--border)] focus:border-[var(--border-focus)]",
              "py-2.5 px-3",
              leftAddon && "pl-9",
              (rightAddon || isPassword) && "pr-10",
              className
            )}
            aria-invalid={Boolean(error)}
            aria-describedby={
              error
                ? `${inputId}-error`
                : hint
                ? `${inputId}-hint`
                : undefined
            }
            {...props}
          />

          {/* Password toggle */}
          {isPassword && (
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="
                absolute right-3 text-[var(--text-muted)]
                hover:text-[var(--text-secondary)] transition-colors
              "
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? (
                <EyeOffIcon />
              ) : (
                <EyeIcon />
              )}
            </button>
          )}

          {/* Right addon (only if not password) */}
          {rightAddon && !isPassword && (
            <div className="absolute right-3 flex items-center text-[var(--text-muted)]">
              {rightAddon}
            </div>
          )}
        </div>

        {/* Error message */}
        {error && (
          <p
            id={`${inputId}-error`}
            role="alert"
            className="text-xs text-red-400 flex items-center gap-1"
          >
            <span aria-hidden="true">⚠</span>
            {error}
          </p>
        )}

        {/* Hint text */}
        {!error && hint && (
          <p
            id={`${inputId}-hint`}
            className="text-xs text-[var(--text-muted)]"
          >
            {hint}
          </p>
        )}
      </div>
    );
  }
);
Input.displayName = "Input";

function EyeIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
      <circle cx="12" cy="12" r="3"/>
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
      <line x1="1" y1="1" x2="23" y2="23"/>
    </svg>
  );
}
