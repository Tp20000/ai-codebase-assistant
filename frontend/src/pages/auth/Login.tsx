/**
 * Login Page
 * AI Codebase Assistant v2.0
 *
 * Features:
 *   - Email + password form with Zod validation
 *   - Inline field-level error messages
 *   - Visible API error banner (never only in console)
 *   - Loading state on submit button
 *   - Animated entrance with Framer Motion
 *   - Redirect to dashboard after successful login
 *   - Link to register page
 */

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate, Link } from "react-router-dom";
import { motion } from "framer-motion";
import toast from "react-hot-toast";

import { useAuthStore } from "@/stores/authStore";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { APP } from "@/utils/constants";

// ── Zod schema ───────────────────────────────────────────────────

const loginSchema = z.object({
  email: z
    .string()
    .min(1, "Email is required")
    .email("Enter a valid email address"),
  password: z
    .string()
    .min(1, "Password is required")
    .min(6, "Password must be at least 6 characters"),
});

type LoginFormData = z.infer<typeof loginSchema>;

// ── Component ─────────────────────────────────────────────────────

/**
 * Login page with email/password form.
 * Redirects authenticated users to the dashboard.
 */
export default function Login() {
  const navigate  = useNavigate();
  const { login, isLoading, error, clearError, user } = useAuthStore();

  // Redirect if already authenticated
  useEffect(() => {
    if (user) navigate("/", { replace: true });
  }, [user, navigate]);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  const onSubmit = async (data: LoginFormData) => {
    clearError();
    try {
      await login(data);
      toast.success("Welcome back!");
      navigate("/", { replace: true });
    } catch {
      // Error is already stored in authStore.error — ErrorBanner handles display
      // Do NOT use console.error only — the UI must show the error
    }
  };

  return (
    <div className="
      min-h-screen flex items-center justify-center
      bg-[var(--bg-primary)] px-4
    ">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: "easeOut" }}
        className="w-full max-w-sm"
      >
        {/* ── Logo + Title ──────────────────────────────────── */}
        <div className="text-center mb-8">
          <div className="
            w-12 h-12 rounded-xl mx-auto mb-4
            bg-gradient-to-br from-blue-500 to-purple-600
            flex items-center justify-center
            shadow-lg shadow-blue-500/30
          ">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none"
              stroke="white" strokeWidth="2" strokeLinecap="round">
              <polyline points="16 18 22 12 16 6"/>
              <polyline points="8 6 2 12 8 18"/>
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)] mb-1">
            {APP.NAME}
          </h1>
          <p className="text-sm text-[var(--text-secondary)]">
            Sign in to your account
          </p>
        </div>

        {/* ── Form card ─────────────────────────────────────── */}
        <div className="
          bg-[var(--bg-secondary)]
          border border-[var(--border)]
          rounded-xl p-6 shadow-xl
        ">
          {/* API error — always visible in UI */}
          <ErrorBanner
            title="Sign in failed"
            message={error}
            onDismiss={clearError}
            className="mb-4"
          />

          <form onSubmit={handleSubmit(onSubmit)} noValidate>
            <div className="flex flex-col gap-4">
              {/* Email */}
              <Input
                label="Email"
                type="email"
                placeholder="you@example.com"
                autoComplete="email"
                autoFocus
                error={errors.email?.message}
                {...register("email")}
              />

              {/* Password */}
              <Input
                label="Password"
                type="password"
                placeholder="••••••••"
                autoComplete="current-password"
                error={errors.password?.message}
                {...register("password")}
              />

              {/* Forgot password link */}
              <div className="flex justify-end -mt-1">
                <Link
                  to="/forgot-password"
                  className="
                    text-xs text-[var(--text-muted)]
                    hover:text-blue-400 transition-colors
                  "
                >
                  Forgot password?
                </Link>
              </div>

              {/* Submit */}
              <Button
                type="submit"
                variant="primary"
                size="lg"
                fullWidth
                isLoading={isLoading}
              >
                Sign In
              </Button>
            </div>
          </form>
        </div>

        {/* ── Register link ─────────────────────────────────── */}
        <p className="text-center text-sm text-[var(--text-secondary)] mt-6">
          Don&apos;t have an account?{" "}
          <Link
            to="/register"
            className="text-blue-400 hover:text-blue-300 font-medium transition-colors"
          >
            Create account →
          </Link>
        </p>

        {/* ── Dev helper ────────────────────────────────────── */}
        {import.meta.env.DEV && (
          <p className="text-center text-xs text-[var(--text-muted)] mt-4">
            Backend: {import.meta.env.VITE_API_URL ?? "http://localhost:8000"}
          </p>
        )}
      </motion.div>
    </div>
  );
}
