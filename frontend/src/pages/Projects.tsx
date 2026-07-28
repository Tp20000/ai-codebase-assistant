/**
 * Projects Page - AI Codebase Assistant v2.0
 *
 * Dedicated page for listing, searching, creating, and deleting projects.
 * Accessible from sidebar "Projects" link -> /projects
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Card, CardHeader, CardBody, CardFooter } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { ProjectCardSkeleton } from "@/components/ui/Skeleton";
import {
  fetchProjects,
  createProject,
  deleteProject,
  getLanguageIcon,
  formatRelativeTime,
  type Project,
  type CreateProjectPayload,
} from "@/services/projectService";

// ── Delete Confirmation Modal ─────────────────────────────────────────────────

interface DeleteModalProps {
  project: Project;
  onConfirm: () => void;
  onCancel: () => void;
  isDeleting: boolean;
}

function DeleteModal({ project, onConfirm, onCancel, isDeleting }: DeleteModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onCancel}
      />
      {/* Modal */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="relative z-10 w-full max-w-md bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl shadow-2xl p-6"
      >
        {/* Icon */}
        <div className="w-12 h-12 rounded-full bg-red-500/10 border border-red-500/20 flex items-center justify-center mx-auto mb-4">
          <span className="text-2xl">🗑️</span>
        </div>

        <h2 className="text-lg font-semibold text-[var(--text-primary)] text-center mb-2">
          Delete Project
        </h2>
        <p className="text-sm text-[var(--text-secondary)] text-center mb-1">
          Are you sure you want to delete
        </p>
        <p className="text-sm font-semibold text-[var(--text-primary)] text-center mb-4">
          "{project.name}"?
        </p>
        <p className="text-xs text-red-400 text-center mb-6 bg-red-500/10 rounded-lg p-3 border border-red-500/20">
          ⚠️ This will permanently delete the project, all uploaded files,
          and all AI embeddings. This action cannot be undone.
        </p>

        <div className="flex gap-3">
          <Button
            variant="ghost"
            className="flex-1"
            onClick={onCancel}
            disabled={isDeleting}
          >
            Cancel
          </Button>
          <button
            onClick={onConfirm}
            disabled={isDeleting}
            className="flex-1 px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-sm font-medium transition-colors flex items-center justify-center gap-2"
          >
            {isDeleting ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Deleting...
              </>
            ) : (
              "Delete Project"
            )}
          </button>
        </div>
      </motion.div>
    </div>
  );
}

// ── Create Project Modal ──────────────────────────────────────────────────────

interface CreateModalProps {
  onClose: () => void;
  onCreated: (project: Project) => void;
}

const LANGUAGES = [
  { value: "python", label: "Python", icon: "🐍" },
  { value: "javascript", label: "JavaScript", icon: "🟨" },
  { value: "typescript", label: "TypeScript", icon: "🔷" },
  { value: "java", label: "Java", icon: "☕" },
  { value: "go", label: "Go", icon: "🐹" },
  { value: "rust", label: "Rust", icon: "🦀" },
  { value: "cpp", label: "C++", icon: "⚡" },
  { value: "mixed", label: "Mixed", icon: "🔀" },
];

function CreateModal({ onClose, onCreated }: CreateModalProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [language, setLanguage] = useState("python");
  const [nameError, setNameError] = useState("");

  const { mutate, isPending } = useMutation({
    mutationFn: (payload: CreateProjectPayload) => createProject(payload),
    onSuccess: (project) => {
      toast.success(`Project "${project.name}" created!`);
      onCreated(project);
    },
    onError: (err: Error) => {
      toast.error(err.message || "Failed to create project");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setNameError("Project name is required");
      return;
    }
    if (name.trim().length < 2) {
      setNameError("Name must be at least 2 characters");
      return;
    }
    setNameError("");
    mutate({ name: name.trim(), description: description.trim(), language });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className="relative z-10 w-full max-w-lg bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl shadow-2xl p-6"
      >
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">
            New Project
          </h2>
          <button
            onClick={onClose}
            className="text-[var(--text-muted)] hover:text-[var(--text-primary)] text-xl leading-none"
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">
              Project Name *
            </label>
            <Input
              value={name}
              onChange={(e) => { setName(e.target.value); setNameError(""); }}
              placeholder="e.g. My Backend API"
              autoFocus
              className={nameError ? "border-red-500" : ""}
            />
            {nameError && (
              <p className="text-xs text-red-400 mt-1">{nameError}</p>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description of this project..."
              rows={3}
              className="w-full px-3 py-2 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border)] text-[var(--text-primary)] text-sm placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--border-focus)] resize-none"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-[var(--text-secondary)] mb-2">
              Primary Language
            </label>
            <div className="grid grid-cols-4 gap-2">
              {LANGUAGES.map((lang) => (
                <button
                  key={lang.value}
                  type="button"
                  onClick={() => setLanguage(lang.value)}
                  className={[
                    "flex flex-col items-center gap-1 p-2 rounded-lg border text-xs transition-colors",
                    language === lang.value
                      ? "border-blue-500 bg-blue-500/10 text-blue-400"
                      : "border-[var(--border)] hover:border-[var(--border-focus)] text-[var(--text-secondary)]",
                  ].join(" ")}
                >
                  <span className="text-lg">{lang.icon}</span>
                  <span>{lang.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="flex gap-3 pt-2">
            <Button variant="ghost" className="flex-1" onClick={onClose} type="button">
              Cancel
            </Button>
            <Button type="submit" className="flex-1" disabled={isPending}>
              {isPending ? "Creating..." : "Create Project"}
            </Button>
          </div>
        </form>
      </motion.div>
    </div>
  );
}

// ── Project Card ──────────────────────────────────────────────────────────────

interface ProjectCardProps {
  project: Project;
  onDelete: (project: Project) => void;
}

function ProjectCard({ project, onDelete }: ProjectCardProps) {
  const navigate = useNavigate();

  const statusColor: Record<string, "success" | "info" | "danger" | "default"> = {
    completed: "success",
    in_progress: "info",
    failed: "danger",
    not_started: "default",
  };

  const statusLabel: Record<string, string> = {
    completed: "Indexed",
    in_progress: "Indexing...",
    failed: "Failed",
    not_started: "Not indexed",
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.18 }}
    >
      <Card className="h-full flex flex-col hover:border-[var(--border-focus)] transition-colors group">
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xl flex-shrink-0">
                {getLanguageIcon(project.language)}
              </span>
              <div className="min-w-0">
                <h3 className="font-semibold text-[var(--text-primary)] truncate text-sm">
                  {project.name}
                </h3>
                <p className="text-xs text-[var(--text-muted)]">
                  {formatRelativeTime(project.created_at)}
                </p>
              </div>
            </div>
            {/* Delete button - visible on hover */}
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(project); }}
              className="flex-shrink-0 opacity-0 group-hover:opacity-100 p-1.5 rounded-md text-[var(--text-muted)] hover:text-red-400 hover:bg-red-500/10 transition-all"
              title="Delete project"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="3,6 5,6 21,6" />
                <path d="M19,6l-1,14a2,2,0,0,1-2,2H8a2,2,0,0,1-2-2L5,6" />
                <path d="M10,11v6M14,11v6" />
                <path d="M9,6V4a1,1,0,0,1,1-1h4a1,1,0,0,1,1,1V6" />
              </svg>
            </button>
          </div>
        </CardHeader>

        <CardBody className="flex-1">
          <p className="text-xs text-[var(--text-secondary)] line-clamp-2 min-h-[2rem]">
            {project.description || "No description provided."}
          </p>

          <div className="flex flex-wrap gap-1.5 mt-3">
            <Badge variant="default">{project.language}</Badge>
            <Badge
              variant={statusColor[project.index_status ?? "not_started"] ?? "default"}
             
            >
              {statusLabel[project.index_status ?? "not_started"]}
            </Badge>
            {project.file_count > 0 && (
              <Badge variant="default">
                📄 {project.file_count} files
              </Badge>
            )}
          </div>
        </CardBody>

        <CardFooter>
          <button
            onClick={() => navigate(`/projects/${project.id}`)}
            className="w-full px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium transition-colors flex items-center justify-center gap-1.5"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" />
              <polyline points="15,3 21,3 21,9" />
              <line x1="10" y1="14" x2="21" y2="3" />
            </svg>
            Open Workspace
          </button>
        </CardFooter>
      </Card>
    </motion.div>
  );
}

// ── Main Projects Page ────────────────────────────────────────────────────────

export default function Projects() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [filterLang, setFilterLang] = useState("all");
  const [showCreate, setShowCreate] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);

  // Fetch projects
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["projects"],
    queryFn: () => fetchProjects(1, 100),
  });

  // Delete mutation
  const { mutate: doDelete, isPending: isDeleting } = useMutation({
    mutationFn: (id: string) => deleteProject(id),
    onSuccess: () => {
      toast.success("Project deleted successfully");
      setDeleteTarget(null);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (err: Error) => {
      toast.error(err.message || "Failed to delete project");
    },
  });

  const projects = data?.items ?? [];

  // Filter projects
  const filtered = projects.filter((p) => {
    const matchSearch =
      !search ||
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      p.description?.toLowerCase().includes(search.toLowerCase());
    const matchLang = filterLang === "all" || p.language === filterLang;
    return matchSearch && matchLang;
  });

  // Unique languages for filter
  const languages = Array.from(new Set(projects.map((p) => p.language))).filter(Boolean);

  return (
    <div className="flex flex-col h-full">
      {/* ── Header ── */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-[var(--border)] bg-[var(--bg-secondary)]">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-bold text-[var(--text-primary)]">Projects</h1>
            <p className="text-sm text-[var(--text-muted)]">
              {projects.length} project{projects.length !== 1 ? "s" : ""} total
            </p>
          </div>
          <Button onClick={() => setShowCreate(true)} className="gap-2">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            New Project
          </Button>
        </div>

        {/* Search + Filter */}
        <div className="flex gap-3 flex-wrap">
          <div className="flex-1 min-w-48">
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search projects..."
              className="h-9 text-sm"
            />
          </div>
          <select
            value={filterLang}
            onChange={(e) => setFilterLang(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border)] text-[var(--text-primary)] text-sm focus:outline-none focus:border-[var(--border-focus)]"
          >
            <option value="all">All Languages</option>
            {languages.map((lang) => (
              <option key={lang} value={lang}>
                {getLanguageIcon(lang)} {lang}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ── Content ── */}
      <div className="flex-1 overflow-auto p-6">
        {/* Error */}
        {isError && (
          <div className="mb-4">
            <ErrorBanner
              message={(error as Error)?.message || "Failed to load projects"}
            />
            <button
              onClick={() => void refetch()}
              className="mt-2 px-3 py-1.5 text-xs rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              Try again
            </button>
          </div>
        )}

        {/* Loading */}
        {isLoading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <ProjectCardSkeleton key={i} />
            ))}
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !isError && filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            {search || filterLang !== "all" ? (
              <>
                <div className="text-5xl mb-4">🔍</div>
                <p className="text-[var(--text-primary)] font-medium mb-1">No matches found</p>
                <p className="text-[var(--text-muted)] text-sm mb-4">
                  Try a different search or filter
                </p>
                <Button variant="ghost" onClick={() => { setSearch(""); setFilterLang("all"); }}>
                  Clear filters
                </Button>
              </>
            ) : (
              <>
                <div className="text-5xl mb-4">📁</div>
                <p className="text-[var(--text-primary)] font-medium mb-1">No projects yet</p>
                <p className="text-[var(--text-muted)] text-sm mb-4">
                  Create your first project to get started
                </p>
                <Button onClick={() => setShowCreate(true)}>
                  Create Project
                </Button>
              </>
            )}
          </div>
        )}

        {/* Grid */}
        {!isLoading && !isError && filtered.length > 0 && (
          <AnimatePresence mode="popLayout">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filtered.map((project) => (
                <ProjectCard
                  key={project.id}
                  project={project}
                  onDelete={setDeleteTarget}
                />
              ))}
            </div>
          </AnimatePresence>
        )}
      </div>

      {/* ── Modals ── */}
      <AnimatePresence>
        {showCreate && (
          <CreateModal
            onClose={() => setShowCreate(false)}
            onCreated={(p) => {
              setShowCreate(false);
              queryClient.invalidateQueries({ queryKey: ["projects"] });
              navigate(`/projects/${p.id}`);
            }}
          />
        )}
        {deleteTarget && (
          <DeleteModal
            project={deleteTarget}
            onCancel={() => setDeleteTarget(null)}
            onConfirm={() => doDelete(deleteTarget.id)}
            isDeleting={isDeleting}
          />
        )}
      </AnimatePresence>
    </div>
  );
}