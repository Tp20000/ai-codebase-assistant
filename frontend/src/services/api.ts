/**
 * Axios API Client - AI Codebase Assistant v2.0
 *
 * Development: uses Vite proxy (/api/v1 -> localhost:8000)
 * Production:  uses VITE_API_URL env variable directly
 */

import axios, { AxiosError, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { STORAGE_KEYS } from "@/utils/constants";

/**
 * Determine the correct base URL:
 * - Production (Vercel): use VITE_API_URL from environment
 * - Local dev: use relative /api/v1 (Vite proxy handles routing)
 */
function getBaseUrl(): string {
  const envUrl = import.meta.env.VITE_API_URL as string | undefined;

  if (envUrl && envUrl.trim() !== "") {
    // Production: VITE_API_URL = https://ai-codebase-backend-r721.onrender.com
    return `${envUrl.replace(/\/$/, "")}/api/v1`;
  }

  // Local development: Vite proxy handles /api -> localhost:8000
  return "/api/v1";
}

const BASE_URL = getBaseUrl();

console.debug(`[API] Base URL: ${BASE_URL}`);

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 120000,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

// ── Request interceptor ───────────────────────────────────────────────────────
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Attach JWT token
    const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // Strip trailing slash from UUID/ID endpoints
    // FastAPI has redirect_slashes=False so /projects/uuid/ = 404
    if (config.url && config.url.length > 1 && config.url.endsWith("/")) {
      const parts = config.url.split("/").filter(Boolean);
      const lastPart = parts[parts.length - 1] ?? "";
      const isUUID = /^[0-9a-f-]{36}$/i.test(lastPart);
      const isNumericId = /^\d+$/.test(lastPart);
      if (isUUID || isNumericId) {
        config.url = config.url.slice(0, -1);
      }
    }

    return config;
  },
  (error: AxiosError) => Promise.reject(error)
);

// ── Response interceptor ──────────────────────────────────────────────────────
apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError) => {
    const req = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    // Auto-refresh token on 401
    if (error.response?.status === 401 && !req._retry) {
      const rt = localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
      if (!rt) {
        localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
        if (window.location.pathname !== "/login") {
          window.location.href = "/login";
        }
        return Promise.reject(error);
      }

      req._retry = true;
      try {
        const resp = await axios.post(`${BASE_URL}/auth/refresh`, {
          refresh_token: rt,
        });
        const { access_token } = resp.data as { access_token: string };
        localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, access_token);
        req.headers.Authorization = `Bearer ${access_token}`;
        return apiClient(req);
      } catch {
        localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
        localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
        if (window.location.pathname !== "/login") {
          window.location.href = "/login";
        }
        return Promise.reject(error);
      }
    }

    return Promise.reject(error);
  }
);

// ── API helpers ───────────────────────────────────────────────────────────────

export async function apiGet<T>(
  url: string,
  params?: Record<string, unknown>
): Promise<T> {
  const r = await apiClient.get<T>(url, { params });
  return r.data;
}

export async function apiPost<T, D = unknown>(
  url: string,
  data?: D
): Promise<T> {
  const r = await apiClient.post<T>(url, data);
  return r.data;
}

export async function apiPut<T, D = unknown>(
  url: string,
  data?: D
): Promise<T> {
  const r = await apiClient.put<T>(url, data);
  return r.data;
}

export async function apiPatch<T, D = unknown>(
  url: string,
  data?: D
): Promise<T> {
  const r = await apiClient.patch<T>(url, data);
  return r.data;
}

export async function apiDelete<T>(url: string): Promise<T> {
  // Always strip trailing slash for DELETE
  const cleanUrl = url.endsWith("/") ? url.slice(0, -1) : url;
  const r = await apiClient.delete<T>(cleanUrl);
  return r.data;
}

export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as
      | { detail?: string | Array<{ msg: string }> }
      | undefined;
    if (typeof data?.detail === "string") return data.detail;
    if (Array.isArray(data?.detail)) {
      return data.detail.map((e) => e.msg).join(", ");
    }
    if (error.response?.status === 429) {
      return "Too many requests — please slow down";
    }
    if (error.message) return error.message;
  }
  if (error instanceof Error) return error.message;
  return "An unexpected error occurred";
}