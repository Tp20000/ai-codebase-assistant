/**
 * Axios API Client - AI Codebase Assistant v2.0
 *
 * Uses relative baseURL "/api/v1" so all requests go through
 * Vite proxy (localhost:5173 -> backend:8000).
 */

import axios, { AxiosError, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { STORAGE_KEYS } from "@/utils/constants";

const BASE_URL = "/api/v1";

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 120000,
  headers: { "Content-Type": "application/json", Accept: "application/json" },
});

// ── Request interceptor ───────────────────────────────────────────────────────
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Attach JWT token
    const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
    if (token) config.headers.Authorization = `Bearer ${token}`;

    // Strip trailing slash from URL to prevent 404 on FastAPI routes
    // FastAPI has redirect_slashes=False so trailing slash = 404
    if (config.url && config.url.length > 1 && config.url.endsWith("/")) {
      // Keep trailing slash only for list endpoints (GET with no path param)
      // e.g. /projects/ is OK, /projects/123/ is NOT OK
      const parts = config.url.split("/").filter(Boolean);
      const lastPart = parts[parts.length - 1];
      const isUUID = /^[0-9a-f-]{36}$/i.test(lastPart);
      const isId = isUUID || /^\d+$/.test(lastPart);
      if (isId) {
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
    const req = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status === 401 && !req._retry) {
      const rt = localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
      if (!rt) {
        localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
        if (window.location.pathname !== "/login") window.location.href = "/login";
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
        if (window.location.pathname !== "/login") window.location.href = "/login";
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
  // Explicitly strip trailing slash for DELETE requests
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
    if (Array.isArray(data?.detail))
      return data.detail.map((e) => e.msg).join(", ");
    if (error.response?.status === 429)
      return "Too many requests — please slow down";
    if (error.message) return error.message;
  }
  if (error instanceof Error) return error.message;
  return "An unexpected error occurred";
}