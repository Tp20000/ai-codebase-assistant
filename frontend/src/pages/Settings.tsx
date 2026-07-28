/**
 * Settings Page - Step 50
 * AI Codebase Assistant v2.0
 *
 * Sections:
 *   - Profile: name, email (read-only), avatar
 *   - Appearance: dark/light theme toggle
 *   - AI Model: select LLM model for chat + agents
 *   - Notifications: email notification toggles
 *   - Account: logout, danger zone
 */

import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import toast from "react-hot-toast";
import { clsx } from "clsx";
import { useAuthStore } from "@/stores/authStore";
import { useUIStore, type Theme } from "@/stores/uiStore";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { APP } from "@/utils/constants";

// ── Section wrapper ───────────────────────────────────────────────

function SettingsSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <Card padding="lg" className="mb-4">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
        {description && (
          <p className="text-xs text-[var(--text-muted)] mt-0.5">{description}</p>
        )}
      </div>
      {children}
    </Card>
  );
}

// ── Toggle switch ─────────────────────────────────────────────────

function Toggle({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: string;
}) {
  return (
    <label className="flex items-center justify-between py-2 cursor-pointer group">
      <div>
        <p className="text-xs font-medium text-[var(--text-primary)]">{label}</p>
        {description && (
          <p className="text-[10px] text-[var(--text-muted)]">{description}</p>
        )}
      </div>
      <button
        onClick={() => onChange(!checked)}
        className={clsx(
          "relative w-9 h-5 rounded-full transition-colors flex-shrink-0",
          checked ? "bg-blue-500" : "bg-[var(--bg-hover)]"
        )}
        role="switch"
        aria-checked={checked}
      >
        <motion.div
          className="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow-sm"
          animate={{ left: checked ? 18 : 2 }}
          transition={{ duration: 0.15 }}
        />
      </button>
    </label>
  );
}

// ── Main Settings Page ────────────────────────────────────────────

export default function Settings() {
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const { theme, setTheme, sidebarCollapsed, setSidebarCollapsed } = useUIStore();

  // Local state for notification preferences
  const [notifications, setNotifications] = useState({
    agentComplete: true,
    indexingComplete: true,
    securityAlerts: true,
    taskFailed: true,
    weeklySummary: false,
  });

  // Local state for model selection
  const [selectedModel, setSelectedModel] = useState("tinyllama");

  const displayName = user?.full_name ?? user?.username ?? "User";
  const initials = displayName
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  const handleLogout = useCallback(() => {
    logout();
    toast.success("Signed out successfully");
    navigate("/login", { replace: true });
  }, [logout, navigate]);

  const handleThemeChange = useCallback(
    (t: Theme) => {
      console.log("THEME CHANGE:", t, "current html class:", document.documentElement.className);
      setTheme(t);
      // Force apply class directly as fallback
      document.documentElement.classList.remove("dark", "light");
      document.documentElement.classList.add(t);
      toast.success(`Theme changed to ${t} mode`);
      console.log("AFTER:", document.documentElement.className);
    },
    [setTheme]
  );

  const handleNotifChange = useCallback(
    (key: keyof typeof notifications, value: boolean) => {
      setNotifications((prev) => ({ ...prev, [key]: value }));
      toast.success("Notification preferences updated");
    },
    []
  );

  const handleModelChange = useCallback((model: string) => {
    setSelectedModel(model);
    toast.success(`Default model set to ${model}`);
  }, []);

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
      >
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">Settings</h1>
          <p className="text-sm text-[var(--text-secondary)] mt-1">
            Manage your account, appearance, and preferences
          </p>
        </div>

        {/* ── Profile ──────────────────────────────────────── */}
        <SettingsSection title="Profile" description="Your account information">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-14 h-14 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-lg font-bold shadow-lg">
              {initials}
            </div>
            <div>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {displayName}
              </p>
              <p className="text-xs text-[var(--text-muted)]">{user?.email}</p>
              {user?.username && (
                <p className="text-[10px] text-[var(--text-muted)]">@{user.username}</p>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border)]">
              <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wide">Account Status</p>
              <p className="text-xs text-green-400 font-medium mt-1">
                {user?.is_active ? "Active" : "Inactive"}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border)]">
              <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-wide">Preferred Model</p>
              <p className="text-xs text-[var(--text-primary)] font-medium mt-1">
                {user?.preferred_model ?? selectedModel}
              </p>
            </div>
          </div>
        </SettingsSection>

        {/* ── Appearance ───────────────────────────────────── */}
        <SettingsSection title="Appearance" description="Customize the look and feel">
          <div className="flex gap-3 mb-4">
            {(["dark", "light"] as const).map((t) => (
              <button
                key={t}
                onClick={() => handleThemeChange(t)}
                className={clsx(
                  "flex-1 flex flex-col items-center gap-2 p-4 rounded-lg border-2 transition-all",
                  theme === t
                    ? "border-blue-500 bg-blue-500/10"
                    : "border-[var(--border)] bg-[var(--bg-tertiary)] hover:border-[var(--border-focus)]"
                )}
              >
                <div className={clsx(
                  "w-10 h-10 rounded-lg flex items-center justify-center text-lg",
                  t === "dark" ? "bg-gray-800 text-white" : "bg-white text-gray-800 border"
                )}>
                  {t === "dark" ? "🌙" : "☀️"}
                </div>
                <span className="text-xs font-medium text-[var(--text-primary)] capitalize">
                  {t} Mode
                </span>
                {theme === t && (
                  <span className="text-[10px] text-blue-400">Active</span>
                )}
              </button>
            ))}
          </div>

          <Toggle
            checked={sidebarCollapsed}
            onChange={setSidebarCollapsed}
            label="Collapse sidebar by default"
            description="Show only icons in the sidebar navigation"
          />
        </SettingsSection>

        {/* ── AI Model ─────────────────────────────────────── */}
        <SettingsSection title="AI Model" description="Select the default LLM for chat and agents">
          <div className="space-y-2">
            {[
              { id: "tinyllama", name: "TinyLlama", desc: "Fast, lightweight (1.1B params)", speed: "⚡ Fast" },
              { id: "llama3.2",  name: "Llama 3.2",  desc: "High quality, slower (8B params)", speed: "🐢 Slower" },
              { id: "codellama", name: "Code Llama", desc: "Code-specialized (7B params)", speed: "🐢 Slower" },
              { id: "mistral",   name: "Mistral",    desc: "Balanced quality/speed (7B params)", speed: "🐢 Slower" },
            ].map((model) => (
              <button
                key={model.id}
                onClick={() => handleModelChange(model.id)}
                className={clsx(
                  "w-full flex items-center justify-between p-3 rounded-lg border transition-all text-left",
                  selectedModel === model.id
                    ? "border-blue-500 bg-blue-500/10"
                    : "border-[var(--border)] bg-[var(--bg-tertiary)] hover:border-[var(--border-focus)]"
                )}
              >
                <div>
                  <p className="text-xs font-semibold text-[var(--text-primary)]">
                    {model.name}
                  </p>
                  <p className="text-[10px] text-[var(--text-muted)]">{model.desc}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-[var(--text-muted)]">{model.speed}</span>
                  {selectedModel === model.id && (
                    <span className="text-blue-400 text-sm">✓</span>
                  )}
                </div>
              </button>
            ))}
          </div>

          <p className="text-[10px] text-[var(--text-muted)] mt-3">
            Note: Only models installed in Ollama are available.
            Currently installed: <span className="text-blue-400">tinyllama</span>
          </p>
        </SettingsSection>

        {/* ── Notifications ────────────────────────────────── */}
        <SettingsSection title="Notifications" description="Control email notification preferences">
          <div className="divide-y divide-[var(--border)]">
            <Toggle
              checked={notifications.agentComplete}
              onChange={(v) => handleNotifChange("agentComplete", v)}
              label="Agent analysis complete"
              description="Get notified when an AI agent finishes analyzing your code"
            />
            <Toggle
              checked={notifications.indexingComplete}
              onChange={(v) => handleNotifChange("indexingComplete", v)}
              label="Indexing complete"
              description="Get notified when project file indexing finishes"
            />
            <Toggle
              checked={notifications.securityAlerts}
              onChange={(v) => handleNotifChange("securityAlerts", v)}
              label="Security alerts"
              description="Get notified about critical security vulnerabilities"
            />
            <Toggle
              checked={notifications.taskFailed}
              onChange={(v) => handleNotifChange("taskFailed", v)}
              label="Task failures"
              description="Get notified when background tasks fail"
            />
            <Toggle
              checked={notifications.weeklySummary}
              onChange={(v) => handleNotifChange("weeklySummary", v)}
              label="Weekly summary"
              description="Receive a weekly project health digest"
            />
          </div>
        </SettingsSection>

        {/* ── About ────────────────────────────────────────── */}
        <SettingsSection title="About">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round">
                <polyline points="16 18 22 12 16 6" />
                <polyline points="8 6 2 12 8 18" />
              </svg>
            </div>
            <div>
              <p className="text-xs font-semibold text-[var(--text-primary)]">{APP.NAME}</p>
              <p className="text-[10px] text-[var(--text-muted)]">Version {APP.VERSION}</p>
            </div>
          </div>
          <p className="text-[10px] text-[var(--text-muted)] leading-relaxed">
            AI-powered codebase analysis assistant. Built with FastAPI, React, LangGraph, Ollama, and ChromaDB.
            All AI runs locally — no data leaves your machine.
          </p>
        </SettingsSection>

        {/* ── Danger Zone ──────────────────────────────────── */}
        <Card padding="lg" className="mb-4 border-red-500/30">
          <h3 className="text-sm font-semibold text-red-400 mb-1">Danger Zone</h3>
          <p className="text-[10px] text-[var(--text-muted)] mb-4">
            Irreversible actions. Be careful.
          </p>
          <div className="flex gap-3">
            <Button variant="danger" size="sm" onClick={handleLogout}>
              Sign Out
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={() => toast("Account deletion not implemented yet", { icon: "🚧" })}
            >
              Delete Account
            </Button>
          </div>
        </Card>

        {/* Footer spacer */}
        <div className="h-8" />
      </motion.div>
    </div>
  );
}