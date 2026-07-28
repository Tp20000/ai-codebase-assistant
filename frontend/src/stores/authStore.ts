/**
 * Auth Store (Zustand)
 * AI Codebase Assistant v2.0
 *
 * Field mapping (from auth.py):
 *   Register: POST { email, username, password, full_name }
 *   Login:    POST { email, password }  (JSON body)
 *   Response: { id, email, username, full_name, is_active, theme, ... }
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { apiPost, apiGet, getErrorMessage } from "@/services/api";
import { STORAGE_KEYS } from "@/utils/constants";

// ── Types matching the actual backend response ───────────────────

export interface BackendUser {
  id: string;
  email: string;
  username: string;
  full_name: string | null;
  is_active: boolean;
  is_verified: boolean;
  preferred_model: string;
  theme: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token?: string;
  token_type: string;
}

// ── Auth state ───────────────────────────────────────────────────

interface AuthState {
  user: BackendUser | null;
  accessToken: string | null;
  refreshToken: string | null;
  isLoading: boolean;
  error: string | null;

  login:      (credentials: { email: string; password: string }) => Promise<void>;
  register:   (data: { name: string; email: string; password: string }) => Promise<void>;
  logout:     () => void;
  clearError: () => void;
  setUser:    (user: BackendUser) => void;
}

// ── Store ────────────────────────────────────────────────────────

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isLoading: false,
      error: null,

      /**
       * Login with email + password (JSON body, not form-encoded).
       * Backend: POST /auth/login { email, password }
       */
      login: async ({ email, password }) => {
        set({ isLoading: true, error: null });
        try {
          // Backend accepts JSON body
          const tokens = await apiPost<TokenResponse>("/auth/login", {
            email,
            password,
          });

          // Store tokens
          localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, tokens.access_token);
          if (tokens.refresh_token) {
            localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, tokens.refresh_token);
          }

          // Fetch user profile
          let user: BackendUser | null = null;
          try {
            user = await apiGet<BackendUser>("/auth/me");
          } catch {
            // If /auth/me doesn't exist, build user from token payload
            try {
              const payload = JSON.parse(
                atob(tokens.access_token.split(".")[1])
              );
              user = {
                id:              payload.sub ?? payload.user_id ?? "",
                email,
                username:        payload.username ?? email.split("@")[0],
                full_name:       payload.full_name ?? null,
                is_active:       true,
                is_verified:     false,
                preferred_model: "tinyllama",
                theme:           "dark",
              };
            } catch {
              user = {
                id: "", email, username: email.split("@")[0],
                full_name: null, is_active: true,
                is_verified: false, preferred_model: "tinyllama", theme: "dark",
              };
            }
          }

          set({
            accessToken:  tokens.access_token,
            refreshToken: tokens.refresh_token ?? null,
            user,
            isLoading: false,
            error: null,
          });
        } catch (err) {
          set({
            isLoading: false,
            error: getErrorMessage(err),
            user: null,
            accessToken: null,
            refreshToken: null,
          });
          throw err;
        }
      },

      /**
       * Register new account.
       * Backend: POST /auth/register { email, username, password, full_name }
       */
      register: async ({ name, email, password }) => {
        set({ isLoading: true, error: null });
        try {
          // Backend requires: email, username, password, full_name (optional)
          const userData = await apiPost<BackendUser>("/auth/register", {
            email,
            username:  name.toLowerCase().replace(/\s+/g, "_").slice(0, 50),
            password,
            full_name: name,
          });

          // After register, login to get tokens
          const tokens = await apiPost<TokenResponse>("/auth/login", {
            email,
            password,
          });

          localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, tokens.access_token);
          if (tokens.refresh_token) {
            localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, tokens.refresh_token);
          }

          set({
            accessToken:  tokens.access_token,
            refreshToken: tokens.refresh_token ?? null,
            user:         userData,
            isLoading:    false,
            error:        null,
          });
        } catch (err) {
          set({ isLoading: false, error: getErrorMessage(err) });
          throw err;
        }
      },

      logout: () => {
        localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
        localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
        localStorage.removeItem(STORAGE_KEYS.USER);
        set({ user: null, accessToken: null, refreshToken: null, error: null });
      },

      clearError: () => set({ error: null }),
      setUser:    (user) => set({ user }),
    }),
    {
      name: "auth-store",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        user:         state.user,
        accessToken:  state.accessToken,
        refreshToken: state.refreshToken,
      }),
    }
  )
);

// ── Selectors ────────────────────────────────────────────────────

export const selectIsAuthenticated = (s: AuthState) =>
  Boolean(s.user && s.accessToken);

export const selectUser = (s: AuthState): BackendUser => {
  if (!s.user) throw new Error("Not authenticated");
  return s.user;
};