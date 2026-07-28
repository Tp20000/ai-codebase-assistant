/**
 * Project API Service - Step 42
 * AI Codebase Assistant v2.0
 */

import { apiGet, apiPost, apiDelete } from "@/services/api";

export interface Project {
  id: string;
  name: string;
  description: string;
  language: string;
  file_count: number;
  indexed: boolean;
  created_at: string;
  updated_at: string;
  owner_id: string;
  chunk_count?: number;
  index_status?: "not_started" | "in_progress" | "completed" | "failed";
}

export interface CreateProjectPayload {
  name: string;
  description?: string;
  language?: string;
}

export interface ProjectListResponse {
  items: Project[];
  total: number;
  page: number;
  per_page: number;
}

/**
 * Fetch all projects. Uses trailing slash to avoid 307 redirect
 * which drops Authorization header in some HTTP clients.
 */
export async function fetchProjects(
  page = 1,
  perPage = 20
): Promise<ProjectListResponse> {
  // Use trailing slash to match FastAPI route directly (avoids 307 redirect)
  const raw = await apiGet<Project[] | ProjectListResponse>("/projects/", {
    page,
    per_page: perPage,
  });
  if (Array.isArray(raw)) {
    return { items: raw, total: raw.length, page: 1, per_page: raw.length };
  }
  // Handle both {items, total} and direct array response shapes
  if ("items" in raw) return raw as ProjectListResponse;
  return { items: [], total: 0, page: 1, per_page: perPage };
}

export async function createProject(
  payload: CreateProjectPayload
): Promise<Project> {
  return apiPost<Project>("/projects/", payload);
}

export async function deleteProject(projectId: string): Promise<void> {
  return apiDelete<void>(`/projects/${projectId}/`);
}

export async function fetchHealth(): Promise<Record<string, unknown>> {
  return apiGet<Record<string, unknown>>("/health");
}

export function getLanguageIcon(language: string): string {
  const icons: Record<string, string> = {
    python: "🐍", javascript: "🟨", typescript: "🔷",
    java: "☕", go: "🐹", rust: "🦀", cpp: "⚡",
    csharp: "🟣", ruby: "💎", php: "🐘", swift: "🧡",
    kotlin: "🎯", mixed: "🔀", unknown: "📄",
  };
  return icons[language?.toLowerCase()] ?? "📄";
}

export function formatRelativeTime(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    if (diffMins < 1)   return "just now";
    if (diffMins < 60)  return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7)   return `${diffDays}d ago`;
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch { return dateStr; }
}