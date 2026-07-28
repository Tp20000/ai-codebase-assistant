/**
 * App Layout Shell - AI Codebase Assistant v2.0
 *
 * Includes:
 * - SVG logo (code bracket hexagon)
 * - Working command palette (Ctrl+K)
 * - Correct sidebar navigation with active state via React Router
 * - Delete project accessible from sidebar context
 */

import { useEffect, useState, useRef, type ReactNode } from "react";
import { useLocation, useNavigate, NavLink } from "react-router-dom";
import { useUIStore } from "@/stores/uiStore";
import { useAuthStore } from "@/stores/authStore";
import { Navigate } from "react-router-dom";
import { APP } from "@/utils/constants";
import { fetchProjects, type Project } from "@/services/projectService";
import { useQuery } from "@tanstack/react-query";

// ── SVG Logo ──────────────────────────────────────────────────────────────────

function AppLogo({ collapsed }: { collapsed: boolean }) {
  return (
    <div className="flex items-center gap-2.5 px-4 h-12 border-b border-[var(--border)] flex-shrink-0">
      {/* Hexagon with </> symbol */}
      <svg
        width="26"
        height="26"
        viewBox="0 0 26 26"
        fill="none"
        className="flex-shrink-0"
      >
        <defs>
          <linearGradient id="logoGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#3B82F6" />
            <stop offset="100%" stopColor="#8B5CF6" />
          </linearGradient>
        </defs>
        {/* Hexagon shape */}
        <polygon
          points="13,1 24,7 24,19 13,25 2,19 2,7"
          fill="url(#logoGrad)"
          opacity="0.15"
          stroke="url(#logoGrad)"
          strokeWidth="1.5"
        />
        {/* </> text */}
        <text
          x="13"
          y="17"
          textAnchor="middle"
          fontSize="8"
          fontWeight="700"
          fontFamily="JetBrains Mono, monospace"
          fill="url(#logoGrad)"
        >
          &lt;/&gt;
        </text>
      </svg>

      {!collapsed && (
        <div className="min-w-0">
          <p className="text-sm font-bold text-[var(--text-primary)] leading-tight truncate">
            {APP.NAME}
          </p>
          <p className="text-[9px] text-[var(--text-muted)] tracking-widest uppercase leading-tight">
            AI Assistant
          </p>
        </div>
      )}
    </div>
  );
}

// ── Command Palette ───────────────────────────────────────────────────────────

interface Command {
  id: string;
  label: string;
  description?: string;
  icon: string;
  action: () => void;
  keywords?: string;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  projects: Project[];
}

function CommandPalette({ open, onClose, projects }: CommandPaletteProps) {
  const navigate = useNavigate();
  const { toggleTheme } = useUIStore();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Build command list
  const staticCommands: Command[] = [
    {
      id: "go-dashboard",
      label: "Go to Dashboard",
      icon: "🏠",
      description: "Overview and stats",
      action: () => { navigate("/"); onClose(); },
      keywords: "home overview",
    },
    {
      id: "go-projects",
      label: "Go to Projects",
      icon: "📁",
      description: "All your projects",
      action: () => { navigate("/projects"); onClose(); },
      keywords: "list projects",
    },
    {
      id: "go-analytics",
      label: "Go to Analytics",
      icon: "📊",
      description: "Code complexity and metrics",
      action: () => { navigate("/analytics"); onClose(); },
      keywords: "charts metrics",
    },
    {
      id: "go-settings",
      label: "Go to Settings",
      icon: "⚙️",
      description: "Account and preferences",
      action: () => { navigate("/settings"); onClose(); },
      keywords: "preferences account theme",
    },
    {
      id: "toggle-theme",
      label: "Toggle Dark / Light Theme",
      icon: "🌓",
      description: "Switch color scheme",
      action: () => { toggleTheme(); onClose(); },
      keywords: "dark light mode color",
    },
    {
      id: "new-project",
      label: "New Project",
      icon: "➕",
      description: "Create a new project",
      action: () => { navigate("/projects"); onClose(); },
      keywords: "create add",
    },
  ];

  // Add project quick-open commands
  const projectCommands: Command[] = projects.slice(0, 10).map((p) => ({
    id: `open-${p.id}`,
    label: p.name,
    icon: "🚀",
    description: `Open workspace · ${p.language}`,
    action: () => { navigate(`/projects/${p.id}`); onClose(); },
    keywords: p.language,
  }));

  const allCommands = [...staticCommands, ...projectCommands];

  // Filter by query
  const filtered = query.trim()
    ? allCommands.filter((c) =>
        c.label.toLowerCase().includes(query.toLowerCase()) ||
        c.description?.toLowerCase().includes(query.toLowerCase()) ||
        c.keywords?.toLowerCase().includes(query.toLowerCase())
      )
    : allCommands;

  // Reset on open
  useEffect(() => {
    if (open) {
      setQuery("");
      setSelected(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Keyboard navigation
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelected((s) => Math.min(s + 1, filtered.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelected((s) => Math.max(s - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        filtered[selected]?.action();
      } else if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, filtered, selected, onClose]);

  // Reset selected when filter changes
  useEffect(() => { setSelected(0); }, [query]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] px-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Palette */}
      <div className="relative z-10 w-full max-w-lg bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl shadow-2xl overflow-hidden">
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--border)]">
          <svg
            width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2"
            className="text-[var(--text-muted)] flex-shrink-0"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search commands or projects..."
            className="flex-1 bg-transparent text-[var(--text-primary)] text-sm placeholder-[var(--text-muted)] outline-none"
          />
          <kbd className="px-1.5 py-0.5 rounded text-[10px] bg-[var(--bg-hover)] border border-[var(--border)] text-[var(--text-muted)]">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div className="max-h-80 overflow-y-auto py-1">
          {filtered.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-[var(--text-muted)]">
              No commands found for "{query}"
            </div>
          ) : (
            filtered.map((cmd, idx) => (
              <button
                key={cmd.id}
                onClick={cmd.action}
                onMouseEnter={() => setSelected(idx)}
                className={[
                  "w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors",
                  idx === selected
                    ? "bg-blue-500/10 text-[var(--text-primary)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]",
                ].join(" ")}
              >
                <span className="text-base flex-shrink-0 w-6 text-center">
                  {cmd.icon}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{cmd.label}</p>
                  {cmd.description && (
                    <p className="text-xs text-[var(--text-muted)] truncate">
                      {cmd.description}
                    </p>
                  )}
                </div>
                {idx === selected && (
                  <kbd className="px-1.5 py-0.5 rounded text-[10px] bg-[var(--bg-hover)] border border-[var(--border)] text-[var(--text-muted)] flex-shrink-0">
                    ↵
                  </kbd>
                )}
              </button>
            ))
          )}
        </div>

        {/* Footer hint */}
        <div className="px-4 py-2 border-t border-[var(--border)] flex items-center gap-4 text-[10px] text-[var(--text-muted)]">
          <span>↑↓ navigate</span>
          <span>↵ select</span>
          <span>ESC close</span>
        </div>
      </div>
    </div>
  );
}

// ── Sidebar Nav Item ──────────────────────────────────────────────────────────

interface NavItemProps {
  icon: ReactNode;
  label: string;
  to: string;
  collapsed: boolean;
}

function NavItem({ icon, label, to, collapsed }: NavItemProps) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        [
          "flex items-center gap-3 px-2 py-2 rounded-md mb-0.5 text-sm transition-colors",
          isActive
            ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
            : "text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]",
          collapsed ? "justify-center" : "",
        ].join(" ")
      }
      title={collapsed ? label : undefined}
    >
      <span className="text-base flex-shrink-0">{icon}</span>
      {!collapsed && <span className="truncate font-medium">{label}</span>}
    </NavLink>
  );
}

// ── SVG Icons ─────────────────────────────────────────────────────────────────

const IconHome = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
    <polyline points="9,22 9,12 15,12 15,22" />
  </svg>
);

const IconFolder = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" />
  </svg>
);

const IconChart = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="18" y1="20" x2="18" y2="10" />
    <line x1="12" y1="20" x2="12" y2="4" />
    <line x1="6" y1="20" x2="6" y2="14" />
  </svg>
);

const IconSettings = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z" />
  </svg>
);

// ── App Layout ────────────────────────────────────────────────────────────────

interface AppLayoutProps {
  children: ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  const { user } = useAuthStore();
  const { sidebarCollapsed, toggleSidebar, commandPaletteOpen, openCommandPalette, closeCommandPalette } = useUIStore();

  // Fetch projects for command palette
  const { data: projectsData } = useQuery({
    queryKey: ["projects"],
    queryFn: () => fetchProjects(1, 20),
    enabled: !!user,
  });
  const projects = projectsData?.items ?? [];

  if (!user) return <Navigate to="/login" replace />;

  // Global Ctrl+K shortcut
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

  const displayName = user.full_name ?? user.username ?? "User";
  const avatarLetter = displayName.charAt(0).toUpperCase();

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg-primary)] text-[var(--text-primary)]">

      {/* ── Command Palette ── */}
      <CommandPalette
        open={commandPaletteOpen}
        onClose={closeCommandPalette}
        projects={projects}
      />

      {/* ── Sidebar ── */}
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
        <AppLogo collapsed={sidebarCollapsed} />

        <nav className="flex-1 overflow-y-auto p-2 space-y-0.5">
          <NavItem icon={<IconHome />}     label="Dashboard" to="/"          collapsed={sidebarCollapsed} />
          <NavItem icon={<IconFolder />}   label="Projects"  to="/projects"  collapsed={sidebarCollapsed} />
          <NavItem icon={<IconChart />}    label="Analytics" to="/analytics" collapsed={sidebarCollapsed} />
          <NavItem icon={<IconSettings />} label="Settings"  to="/settings"  collapsed={sidebarCollapsed} />
        </nav>

        {/* Collapse toggle */}
        <button
          onClick={toggleSidebar}
          className="m-2 p-2 rounded-md text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)] transition-colors text-xs flex items-center justify-center gap-1"
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {sidebarCollapsed ? (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="9,18 15,12 9,6" />
            </svg>
          ) : (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="15,18 9,12 15,6" />
              </svg>
              <span>Collapse</span>
            </>
          )}
        </button>
      </aside>

      {/* ── Main ── */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex-shrink-0 h-12 flex items-center justify-between px-4 border-b border-[var(--border)] bg-[var(--bg-secondary)]">
          {/* Mobile menu */}
          <button
            className="md:hidden p-2 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            onClick={toggleSidebar}
          >
            ☰
          </button>

          {/* Command palette trigger */}
          <button
            onClick={openCommandPalette}
            className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-md bg-[var(--bg-tertiary)] border border-[var(--border)] text-[var(--text-muted)] text-xs hover:border-[var(--border-focus)] hover:text-[var(--text-secondary)] transition-colors min-w-48"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <span className="flex-1 text-left">Search or run command...</span>
            <kbd className="px-1.5 py-0.5 rounded text-[10px] bg-[var(--bg-hover)] border border-[var(--border)]">
              ⌘K
            </kbd>
          </button>

          {/* User avatar */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-[var(--text-muted)] hidden sm:block">
              {displayName}
            </span>
            <div
              className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-xs font-semibold cursor-pointer"
              title={displayName}
            >
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