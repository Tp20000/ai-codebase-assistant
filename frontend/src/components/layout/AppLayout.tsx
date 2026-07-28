/**
 * App Layout Shell
 * AI Codebase Assistant v2.0
 */

import { useEffect, type ReactNode } from "react";
import { useUIStore } from "@/stores/uiStore";
import { useAuthStore } from "@/stores/authStore";
import { Navigate } from "react-router-dom";
import { APP } from "@/utils/constants";

interface AppLayoutProps {
  children: ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  const { user } = useAuthStore();
  const { sidebarCollapsed, toggleSidebar, openCommandPalette } = useUIStore();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  // Global keyboard shortcut: Ctrl+K -> command palette
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        openCommandPalette();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [openCommandPalette]);

  // Display name: prefer full_name, fall back to username
  const displayName = user.full_name ?? user.username ?? "User";
  const avatarLetter = displayName.charAt(0).toUpperCase();

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg-primary)] text-[var(--text-primary)]">
      {/* ── Sidebar ─────────────────────────────────────── */}
      <aside
        className={[
          "flex-shrink-0 flex flex-col",
          "border-r border-[var(--border)]",
          "bg-[var(--bg-secondary)]",
          "transition-all duration-200 ease-in-out",
          sidebarCollapsed ? "w-14" : "w-60",
          "hidden md:flex",
        ].join(" ")}
      >
        {/* Logo */}
        <div className="flex items-center gap-2 px-4 h-12 border-b border-[var(--border)]">
          <div className="w-6 h-6 rounded bg-gradient-to-br from-blue-500 to-purple-600 flex-shrink-0" />
          {!sidebarCollapsed && (
            <span className="font-semibold text-sm text-[var(--text-primary)] truncate">
              {APP.NAME}
            </span>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto p-2">
          <SidebarNavItem icon="🏠" label="Dashboard"  href="/"          collapsed={sidebarCollapsed} />
          <SidebarNavItem icon="📁" label="Projects"   href="/projects"  collapsed={sidebarCollapsed} />
          <SidebarNavItem icon="📊" label="Analytics"  href="/analytics" collapsed={sidebarCollapsed} />
          <SidebarNavItem icon="⚙️" label="Settings"   href="/settings"  collapsed={sidebarCollapsed} />
        </nav>

        {/* Collapse toggle */}
        <button
          onClick={toggleSidebar}
          className="m-2 p-2 rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition-colors text-sm flex items-center justify-center"
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {sidebarCollapsed ? "→" : "←"}
        </button>
      </aside>

      {/* ── Main content ──────────────────────────────── */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex-shrink-0 h-12 flex items-center justify-between px-4 border-b border-[var(--border)] bg-[var(--bg-secondary)]">
          <button
            className="md:hidden p-2 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            onClick={toggleSidebar}
          >
            ☰
          </button>

          <button
            onClick={openCommandPalette}
            className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-md bg-[var(--bg-tertiary)] border border-[var(--border)] text-[var(--text-muted)] text-xs hover:border-[var(--border-focus)] hover:text-[var(--text-secondary)] transition-colors"
          >
            <span>Search or run command...</span>
            <kbd className="px-1.5 py-0.5 rounded text-[10px] bg-[var(--bg-hover)] border border-[var(--border)]">⌘K</kbd>
          </button>

          <div className="flex items-center gap-2">
            <span className="text-xs text-[var(--text-muted)] hidden sm:block">
              {displayName}
            </span>
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-xs font-semibold">
              {avatarLetter}
            </div>
          </div>
        </header>

        {/* Page content */}
        <div className="flex-1 overflow-auto">
          {children}
        </div>
      </main>
    </div>
  );
}

interface SidebarNavItemProps {
  icon: string;
  label: string;
  href: string;
  collapsed: boolean;
}

function SidebarNavItem({ icon, label, href, collapsed }: SidebarNavItemProps) {
  const isActive = window.location.pathname === href;
  return (
    <a
      href={href}
      className={[
        "flex items-center gap-3 px-2 py-2 rounded-md mb-0.5 text-sm transition-colors",
        isActive
          ? "bg-[var(--bg-hover)] text-[var(--text-primary)]"
          : "text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]",
        collapsed ? "justify-center" : "",
      ].join(" ")}
      title={collapsed ? label : undefined}
    >
      <span className="text-base flex-shrink-0">{icon}</span>
      {!collapsed && <span className="truncate">{label}</span>}
    </a>
  );
}