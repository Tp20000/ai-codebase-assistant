/**
 * Dashboard Page - Step 42
 * AI Codebase Assistant v2.0
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import toast from "react-hot-toast";
import { clsx } from "clsx";

import { useAuthStore } from "@/stores/authStore";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { Card, CardHeader, CardBody, CardFooter } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Skeleton, StatCardSkeleton, ProjectCardSkeleton } from "@/components/ui/Skeleton";
import {
  fetchProjects,
  fetchHealth,
  createProject,
  getLanguageIcon,
  formatRelativeTime,
  type Project,
} from "@/services/projectService";

// ── Stat Widget ───────────────────────────────────────────────────

function StatWidget({
  label,
  value,
  icon,
  sub,
  color = "#3B82F6",
}: {
  label: string;
  value: string | number;
  icon: string;
  sub?: string;
  color?: string;
}) {
  return (
    <Card padding="md">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wide mb-1">{label}</p>
          <p className="text-2xl font-bold text-[var(--text-primary)]">{value}</p>
          {sub && <p className="text-xs text-[var(--text-muted)] mt-1">{sub}</p>}
        </div>
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center text-lg"
          style={{ background: `${color}20` }}
        >
          {icon}
        </div>
      </div>
    </Card>
  );
}

// ── Project Card ──────────────────────────────────────────────────

function ProjectCard({ project, onClick }: { project: Project; onClick: () => void }) {
  const icon = getLanguageIcon(project.language);
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
    >
      <Card onClick={onClick} padding="md" className="cursor-pointer">
        <CardHeader>
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-xl flex-shrink-0">{icon}</span>
            <h3 className="font-semibold text-sm text-[var(--text-primary)] truncate">
              {project.name}
            </h3>
          </div>
          <Badge variant={project.indexed ? "success" : "default"} dot>
            {project.indexed ? "Indexed" : "Not indexed"}
          </Badge>
        </CardHeader>
        <CardBody>
          {project.description ? (
            <p className="text-xs text-[var(--text-secondary)] line-clamp-2 mb-3">
              {project.description}
            </p>
          ) : (
            <p className="text-xs text-[var(--text-muted)] italic mb-3">No description</p>
          )}
        </CardBody>
        <CardFooter>
          <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
            <div className="flex items-center gap-3">
              <span>📁 {project.file_count ?? 0} files</span>
              <span className="capitalize">{project.language || "unknown"}</span>
            </div>
            <span>{formatRelativeTime(project.updated_at ?? project.created_at)}</span>
          </div>
        </CardFooter>
      </Card>
    </motion.div>
  );
}

// ── Create Project Modal ──────────────────────────────────────────

function CreateProjectModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [language, setLanguage] = useState("python");
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: createProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      toast.success("Project created!");
      onClose();
    },
    onError: (err: Error) => setError(err.message ?? "Failed to create project"),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.15 }}
        className="relative w-full max-w-md bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl shadow-2xl p-6"
      >
        <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-1">
          Create New Project
        </h2>
        <p className="text-sm text-[var(--text-muted)] mb-5">
          Upload code files after creating the project.
        </p>
        <ErrorBanner message={error} onDismiss={() => setError(null)} className="mb-4" />
        <form onSubmit={(e) => {
          e.preventDefault();
          if (!name.trim()) { setError("Project name is required"); return; }
          setError(null);
          mutation.mutate({ name: name.trim(), description: description.trim(), language });
        }}>
          <div className="flex flex-col gap-4">
            <Input
              label="Project Name"
              placeholder="My Awesome Project"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
            <Input
              label="Description (optional)"
              placeholder="What does this project do?"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wide">
                Primary Language
              </label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="w-full rounded-lg text-sm bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] focus:border-[var(--border-focus)] focus:outline-none py-2.5 px-3"
              >
                {[
                  ["python","🐍 Python"],["javascript","🟨 JavaScript"],
                  ["typescript","🔷 TypeScript"],["java","☕ Java"],
                  ["go","🐹 Go"],["rust","🦀 Rust"],["cpp","⚡ C++"],["mixed","🔀 Mixed"],
                ].map(([val, label]) => (
                  <option key={val} value={val}>{label}</option>
                ))}
              </select>
            </div>
            <div className="flex gap-3 pt-1">
              <Button type="button" variant="secondary" fullWidth onClick={onClose}>Cancel</Button>
              <Button type="submit" variant="primary" fullWidth isLoading={mutation.isPending}>
                Create Project
              </Button>
            </div>
          </div>
        </form>
      </motion.div>
    </div>
  );
}

// ── Health Indicator ──────────────────────────────────────────────

function HealthIndicator() {
  const { data, isLoading } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
    retry: false,
  });
  if (isLoading) return <Skeleton className="h-5 w-28" />;
  const status = (data as { status?: string })?.status ?? "unknown";
  const isOk = status === "ok" || status === "healthy";
  return <Badge variant={isOk ? "success" : "warning"} dot className="text-[11px]">Backend {isOk ? "online" : status}</Badge>;
}

// ── Dashboard ─────────────────────────────────────────────────────

export default function Dashboard() {
  const { user } = useAuthStore();
  const navigate = useNavigate();
  const [showCreateModal, setShowCreateModal] = useState(false);

  const displayName = user?.full_name ?? user?.username ?? "User";

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["projects"],
    queryFn: () => fetchProjects(1, 20),
    retry: 1,
  });

  const projects: Project[] = Array.isArray(data)
    ? data
    : (data?.items ?? []);

  const totalFiles = projects.reduce((sum, p) => sum + (p.file_count ?? 0), 0);
  const indexedCount = projects.filter((p) => p.indexed).length;

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6 gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">
            Welcome back, {displayName}! 👋
          </h1>
          <div className="flex items-center gap-3 mt-1">
            <p className="text-sm text-[var(--text-secondary)]">
              {projects.length > 0
                ? `You have ${projects.length} project${projects.length === 1 ? "" : "s"}`
                : "Get started by creating your first project"}
            </p>
            <HealthIndicator />
          </div>
        </div>
        <Button variant="primary" onClick={() => setShowCreateModal(true)} leftIcon={<span>+</span>}>
          New Project
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <StatCardSkeleton key={i} />)
        ) : (
          <>
            <StatWidget label="Projects" value={projects.length} icon="📁" color="#3B82F6" />
            <StatWidget label="Files Indexed" value={totalFiles.toLocaleString()} icon="📄" color="#10B981" sub={`${indexedCount} projects indexed`} />
            <StatWidget label="Languages" value={new Set(projects.map(p => p.language)).size} icon="💻" color="#8B5CF6" />
            <StatWidget label="Agents Available" value={7} icon="🤖" color="#F59E0B" sub="Ready to analyze" />
          </>
        )}
      </div>

      {/* Error */}
      {isError && (
        <ErrorBanner
          title="Failed to load projects"
          message={(error as Error)?.message ?? "Could not connect"}
          className="mb-6"
        />
      )}

      {/* Projects section */}
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-base font-semibold text-[var(--text-primary)]">Your Projects</h2>
        {!isLoading && projects.length > 0 && (
          <button onClick={() => refetch()} className="text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors">
            Refresh
          </button>
        )}
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => <ProjectCardSkeleton key={i} />)}
        </div>
      )}

      {/* Empty */}
      {!isLoading && !isError && projects.length === 0 && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col items-center justify-center py-20 text-center"
        >
          <div className="text-5xl mb-4">🚀</div>
          <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-2">No projects yet</h3>
          <p className="text-sm text-[var(--text-secondary)] max-w-sm mb-6">
            Create your first project, upload your codebase, and start asking AI questions about your code.
          </p>
          <Button variant="primary" size="lg" onClick={() => setShowCreateModal(true)} leftIcon={<span>+</span>}>
            Create First Project
          </Button>
        </motion.div>
      )}

      {/* Project grid */}
      {!isLoading && projects.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onClick={() => navigate(`/projects/${project.id}`)}
            />
          ))}
        </div>
      )}

      {/* Quick actions */}
      {!isLoading && (
        <div className="mt-8">
          <h2 className="text-base font-semibold text-[var(--text-primary)] mb-3">Quick Actions</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { icon: "🔍", label: "Security Scan",  color: "#F59E0B" },
              { icon: "📚", label: "Generate Docs",  color: "#3B82F6" },
              { icon: "🧪", label: "Write Tests",    color: "#10B981" },
              { icon: "⚡", label: "Analyze Perf",   color: "#8B5CF6" },
            ].map((action) => (
              <button
                key={action.label}
                onClick={() => toast("Select a project first to run agents", { icon: "💡" })}
                className="flex flex-col items-center gap-2 p-4 rounded-xl border border-[var(--border)] bg-[var(--bg-secondary)] hover:bg-[var(--bg-tertiary)] hover:border-[var(--border-focus)] transition-colors"
              >
                <span className="text-2xl">{action.icon}</span>
                <span className="text-xs font-medium text-[var(--text-secondary)]">{action.label}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Modal */}
      <AnimatePresence>
        {showCreateModal && <CreateProjectModal onClose={() => setShowCreateModal(false)} />}
      </AnimatePresence>
    </div>
  );
}