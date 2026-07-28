/**
 * UI Store - clean rebuild
 * AI Codebase Assistant v2.0
 *
 * Supports:
 *  - dark/light theme
 *  - sidebar open / compact / collapsed
 *  - command palette
 *  - active panel
 *  - notifications
 */

import { create } from "zustand";
import { devtools, persist, createJSONStorage } from "zustand/middleware";
import { STORAGE_KEYS } from "@/utils/constants";

export type Theme = "dark" | "light";
export type ActivePanel = "chat" | "agents" | "analytics" | "settings";

interface Notification {
  id: string;
  type: "success" | "error" | "warning" | "info";
  title: string;
  message: string;
  timestamp: number;
  read: boolean;
}

interface UIState {
  // Theme
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;

  // Sidebar
  sidebarOpen: boolean;
  sidebarCompact: boolean;
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebarCompact: (compact: boolean) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;

  // Command Palette
  commandPaletteOpen: boolean;
  openCommandPalette: () => void;
  closeCommandPalette: () => void;

  // Active Panel
  activePanel: ActivePanel;
  setActivePanel: (panel: ActivePanel) => void;

  // Active Project
  activeProjectId: string | null;
  setActiveProjectId: (id: string | null) => void;

  // Notifications
  notifications: Notification[];
  addNotification: (n: Omit<Notification, "id" | "timestamp" | "read">) => void;
  markNotificationRead: (id: string) => void;
  clearNotifications: () => void;
  unreadCount: () => number;
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;

  // Apply class
  root.classList.remove("dark", "light");
  root.classList.add(theme);

  // Apply CSS variables directly
  if (theme === "light") {
    root.style.setProperty("--bg-primary", "#ffffff");
    root.style.setProperty("--bg-secondary", "#f6f8fa");
    root.style.setProperty("--bg-tertiary", "#eaeef2");
    root.style.setProperty("--bg-hover", "#d0d7de");
    root.style.setProperty("--border", "#d0d7de");
    root.style.setProperty("--border-focus", "#3B82F6");
    root.style.setProperty("--text-primary", "#1f2328");
    root.style.setProperty("--text-secondary", "#57606a");
    root.style.setProperty("--text-muted", "#8c959f");
    root.style.setProperty("--scrollbar-track", "#f6f8fa");
    root.style.setProperty("--scrollbar-thumb", "#d0d7de");
  } else {
    root.style.setProperty("--bg-primary", "#0d1117");
    root.style.setProperty("--bg-secondary", "#161b22");
    root.style.setProperty("--bg-tertiary", "#21262d");
    root.style.setProperty("--bg-hover", "#30363d");
    root.style.setProperty("--border", "#30363d");
    root.style.setProperty("--border-focus", "#3B82F6");
    root.style.setProperty("--text-primary", "#f0f6fc");
    root.style.setProperty("--text-secondary", "#8b949e");
    root.style.setProperty("--text-muted", "#484f58");
    root.style.setProperty("--scrollbar-track", "#161b22");
    root.style.setProperty("--scrollbar-thumb", "#30363d");
  }

  // Persist theme explicitly
  try {
    localStorage.setItem(STORAGE_KEYS.THEME, theme);
  } catch {
    // ignore
  }

  // Meta theme color
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    meta.setAttribute("content", theme === "dark" ? "#0d1117" : "#ffffff");
  }
}

export const useUIStore = create<UIState>()(
  devtools(
    persist(
      (set, get) => ({
        // Theme
        theme: "dark",
        toggleTheme: () => {
          const next: Theme = get().theme === "dark" ? "light" : "dark";
          get().setTheme(next);
        },
        setTheme: (theme: Theme) => {
          applyTheme(theme);
          set({ theme }, false, "ui/set-theme");
        },

        // Sidebar
        sidebarOpen: true,
        sidebarCompact: false,
        sidebarCollapsed: false,
        toggleSidebar: () =>
          set(
            (s) => ({ sidebarOpen: !s.sidebarOpen }),
            false,
            "ui/toggle-sidebar"
          ),
        setSidebarCompact: (compact: boolean) =>
          set({ sidebarCompact: compact }, false, "ui/set-sidebar-compact"),
        setSidebarCollapsed: (collapsed: boolean) =>
          set(
            { sidebarCollapsed: collapsed, sidebarCompact: collapsed },
            false,
            "ui/set-sidebar-collapsed"
          ),

        // Command Palette
        commandPaletteOpen: false,
        openCommandPalette: () =>
          set({ commandPaletteOpen: true }, false, "ui/open-command-palette"),
        closeCommandPalette: () =>
          set({ commandPaletteOpen: false }, false, "ui/close-command-palette"),

        // Active Panel
        activePanel: "chat",
        setActivePanel: (panel: ActivePanel) =>
          set({ activePanel: panel }, false, "ui/set-active-panel"),

        // Active Project
        activeProjectId: null,
        setActiveProjectId: (id: string | null) =>
          set({ activeProjectId: id }, false, "ui/set-active-project"),

        // Notifications
        notifications: [],
        addNotification: (n) =>
          set(
            (s) => ({
              notifications: [
                {
                  ...n,
                  id: crypto.randomUUID(),
                  timestamp: Date.now(),
                  read: false,
                },
                ...s.notifications,
              ].slice(0, 50),
            }),
            false,
            "ui/add-notification"
          ),
        markNotificationRead: (id: string) =>
          set(
            (s) => ({
              notifications: s.notifications.map((n) =>
                n.id === id ? { ...n, read: true } : n
              ),
            }),
            false,
            "ui/mark-notification-read"
          ),
        clearNotifications: () =>
          set({ notifications: [] }, false, "ui/clear-notifications"),
        unreadCount: () =>
          get().notifications.filter((n) => !n.read).length,
      }),
      {
        name: "aca-ui-store",
        storage: createJSONStorage(() => localStorage),
        partialize: (state) => ({
          theme: state.theme,
          sidebarOpen: state.sidebarOpen,
          sidebarCompact: state.sidebarCompact,
          sidebarCollapsed: state.sidebarCollapsed,
        }),
        onRehydrateStorage: () => (state) => {
          if (state?.theme) {
            applyTheme(state.theme);
          }
        },
      }
    ),
    { name: "UIStore" }
  )
);