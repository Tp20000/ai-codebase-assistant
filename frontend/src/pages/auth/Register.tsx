/**
 * Register Page
 * AI Codebase Assistant v2.0
 *
 * Features:
 *   - Name + email + password + confirm-password form
 *   - Zod schema with password strength validation
 *   - Real-time password strength indicator
 *   - Inline field errors (visible in UI, not just console)
 *   - Loading state + API error display
 *   - Animated entrance
 *   - Redirect to dashboard after successful registration
 */

import { useEffect } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate, Link } from "react-router-dom";
import { motion } from "framer-motion";
import toast from "react-hot-toast";
import { clsx } from "clsx";

import { useAuthStore } from "@/stores/authStore";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { APP } from "@/utils/constants";

// ── Password strength helpers ────────────────────────────────────

interface StrengthResult {
  score: number;        // 0-4
  label: string;
  color: string;
  checks: {
    label: string;
    passed: boolean;
  }[];
}

function getPasswordStrength(password: string): StrengthResult {
  const checks = [
    { label: "At least 8 characters",   passed: password.length >= 8 },
    { label: "Uppercase letter",         passed: /[A-Z]/.test(password) },
    { label: "Lowercase letter",         passed: /[a-z]/.test(password) },
    { label: "Number",                   passed: /\d/.test(password) },
    { label: "Special character",        passed: /[^A-Za-z0-9]/.test(password) },
  ];
  const score = checks.filter((c) => c.passed).length;

  const levels: Array<{ label: string; color: string }> = [
    { label: "Very weak",  color: "#EF4444" },
    { label: "Weak",       color: "#F59E0B" },
    { label: "Fair",       color: "#EAB308" },
    { label: "Good",       color: "#10B981" },
    { label: "Strong",     color: "#3B82F6" },
  ];

  return { score, ...levels[Math.min(score, 4)], checks };
}

// ── Zod schema ───────────────────────────────────────────────────

const registerSchema = z
  .object({
    name: z
      .string()
      .min(2, "Name must be at least 2 characters")
      .max(50, "Name too long"),
    email: z
      .string()
      .min(1, "Email is required")
      .email("Enter a valid email address"),
    password: z
      .string()
      .min(8, "Password must be at least 8 characters")
      .regex(/[A-Z]/, "Must contain an uppercase letter")
      .regex(/[0-9]/, "Must contain a number"),
    confirmPassword: z.string().min(1, "Please confirm your password"),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

type RegisterFormData = z.infer<typeof registerSchema>;

// ── Component ─────────────────────────────────────────────────────

/**
 * Register page with full form validation and password strength meter.
 */
export default function Register() {
  const navigate = useNavigate();
  const { register: registerUser, isLoading, error, clearError, user } =
    useAuthStore();

  // Redirect if already authenticated
  useEffect(() => {
    if (user) navigate("/", { replace: true });
  }, [user, navigate]);

  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
    defaultValues: { name: "", email: "", password: "", confirmPassword: "" },
    mode: "onTouched",
  });

  // Watch password for strength indicator
  const watchedPassword = useWatch({ control, name: "password", defaultValue: "" });
  const strength = getPasswordStrength(watchedPassword);

  const onSubmit = async (data: RegisterFormData) => {
    clearError();
    try {
      await registerUser({
        name: data.name,
        email: data.email,
        password: data.password,
      });
      toast.success("Account created! Welcome aboard 🎉");
      navigate("/", { replace: true });
    } catch {
      // Error displayed via ErrorBanner — never only in console
    }
  };

  return (
    <div className="
      min-h-screen flex items-center justify-center
      bg-[var(--bg-primary)] px-4 py-8
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
            Create Account
          </h1>
          <p className="text-sm text-[var(--text-secondary)]">
            Join {APP.NAME}
          </p>
        </div>

        {/* ── Form card ─────────────────────────────────────── */}
        <div className="
          bg-[var(--bg-secondary)]
          border border-[var(--border)]
          rounded-xl p-6 shadow-xl
        ">
          {/* API error */}
          <ErrorBanner
            title="Registration failed"
            message={error}
            onDismiss={clearError}
            className="mb-4"
          />

          <form onSubmit={handleSubmit(onSubmit)} noValidate>
            <div className="flex flex-col gap-4">
              {/* Name */}
              <Input
                label="Full Name"
                type="text"
                placeholder="Alice Johnson"
                autoComplete="name"
                autoFocus
                error={errors.name?.message}
                {...register("name")}
              />

              {/* Email */}
              <Input
                label="Email"
                type="email"
                placeholder="alice@example.com"
                autoComplete="email"
                error={errors.email?.message}
                {...register("email")}
              />

              {/* Password */}
              <div>
                <Input
                  label="Password"
                  type="password"
                  placeholder="••••••••"
                  autoComplete="new-password"
                  error={errors.password?.message}
                  {...register("password")}
                />

                {/* Password strength meter */}
                {watchedPassword.length > 0 && (
                  <div className="mt-2">
                    {/* Strength bar */}
                    <div className="flex gap-1 mb-1.5">
                      {[0, 1, 2, 3, 4].map((i) => (
                        <div
                          key={i}
                          className="h-1 flex-1 rounded-full transition-all duration-200"
                          style={{
                            backgroundColor:
                              i < strength.score
                                ? strength.color
                                : "var(--bg-hover)",
                          }}
                        />
                      ))}
                    </div>
                    {/* Strength label */}
                    <div className="flex items-center justify-between">
                      <span
                        className="text-xs font-medium"
                        style={{ color: strength.color }}
                      >
                        {strength.label}
                      </span>
                    </div>
                    {/* Requirement checklist */}
                    <ul className="mt-1.5 grid grid-cols-2 gap-x-2 gap-y-0.5">
                      {strength.checks.map((check) => (
                        <li
                          key={check.label}
                          className={clsx(
                            "text-[11px] flex items-center gap-1",
                            check.passed
                              ? "text-green-400"
                              : "text-[var(--text-muted)]"
                          )}
                        >
                          <span aria-hidden="true">
                            {check.passed ? "✓" : "○"}
                          </span>
                          {check.label}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Confirm Password */}
              <Input
                label="Confirm Password"
                type="password"
                placeholder="••••••••"
                autoComplete="new-password"
                error={errors.confirmPassword?.message}
                {...register("confirmPassword")}
              />

              {/* Terms hint */}
              <p className="text-xs text-[var(--text-muted)] text-center -mt-1">
                By creating an account you agree to our{" "}
                <span className="text-blue-400">Terms of Service</span>.
              </p>

              {/* Submit */}
              <Button
                type="submit"
                variant="primary"
                size="lg"
                fullWidth
                isLoading={isLoading}
              >
                Create Account
              </Button>
            </div>
          </form>
        </div>

        {/* ── Login link ────────────────────────────────────── */}
        <p className="text-center text-sm text-[var(--text-secondary)] mt-6">
          Already have an account?{" "}
          <Link
            to="/login"
            className="text-blue-400 hover:text-blue-300 font-medium transition-colors"
          >
            Sign in →
          </Link>
        </p>
      </motion.div>
    </div>
  );
}
