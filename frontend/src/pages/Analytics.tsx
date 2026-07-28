/**
 * Analytics Page - Step 49 (fixed: compute complexity without backend endpoint)
 */

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { DependencyGraph, DependencyGraphEmpty } from "@/components/graphs/DependencyGraph";
import { ComplexityChart } from "@/components/analytics/ComplexityChart";
import { LanguagePieChart } from "@/components/analytics/LanguagePieChart";
import { HotspotMap } from "@/components/analytics/HotspotMap";
import { Badge } from "@/components/ui/Badge";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { apiGet, apiPost } from "@/services/api";
import { fetchProjects, type Project } from "@/services/projectService";
import { fetchProjectFiles, type ProjectFileInfo } from "@/services/fileService";

type AnalyticsTab = "graph" | "complexity" | "languages" | "hotspots";

/** Approximate cyclomatic complexity from source text */
function estimateComplexity(content: string): number {
  const patterns = [
    /\bif\b/g, /\belif\b/g, /\belse\b/g,
    /\bfor\b/g, /\bwhile\b/g,
    /\bexcept\b/g, /\bwith\b/g,
    /\band\b/g, /\bor\b/g,
    /\?\s/g,
    /&&/g, /\|\|/g,
    /\bcase\b/g, /\bswitch\b/g,
  ];
  let count = 1;
  for (const p of patterns) {
    const m = content.match(p);
    if (m) count += m.length;
  }
  return Math.min(count, 50);
}

function ccToGrade(cc: number): string {
  if (cc <= 5)  return "A";
  if (cc <= 10) return "B";
  if (cc <= 15) return "C";
  if (cc <= 20) return "D";
  return "F";
}

function maintainabilityIndex(cc: number, lines: number): number {
  const mi = Math.max(0, 171 - 5.2 * Math.log(Math.max(1, lines)) - 0.23 * cc);
  return Math.round((mi / 171) * 100);
}

export default function Analytics() {
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<AnalyticsTab>("graph");

  const { data: projectsData } = useQuery({
    queryKey: ["projects"],
    queryFn: () => fetchProjects(1, 50),
  });
  const projects = Array.isArray(projectsData) ? projectsData : projectsData?.items ?? [];

  const { data: files = [], isLoading: filesLoading } = useQuery({
    queryKey: ["analytics-files", selectedProjectId],
    queryFn: () => fetchProjectFiles(selectedProjectId!),
    enabled: Boolean(selectedProjectId),
  });

  // Fetch file contents
  const { data: filesWithContent = [], isLoading: contentsLoading } = useQuery({
    queryKey: ["analytics-contents", selectedProjectId, files.length],
    queryFn: async () => {
      return await Promise.all(
        files.slice(0, 80).map(async (f) => {
          try {
            const detail = await apiGet<ProjectFileInfo>(
              `/projects/${selectedProjectId}/files/${f.id}`
            );
            return {
              path: f.file_path,
              content: detail.content ?? "",
              language: f.language || "unknown",
              lines: f.line_count || 0,
            };
          } catch {
            return { path: f.file_path, content: "", language: f.language || "unknown", lines: f.line_count || 0 };
          }
        })
      );
    },
    enabled: Boolean(selectedProjectId) && files.length > 0,
  });

  // Dependency graph
  const { data: graphData, isLoading: graphLoading } = useQuery({
    queryKey: ["dep-graph", selectedProjectId, filesWithContent.length],
    queryFn: async () => {
      const payload = filesWithContent.filter((f) => f.content);
      if (payload.length === 0) return null;
      try {
        return await apiPost<{ nodes: unknown[]; edges: unknown[]; metadata: unknown }>(
          "/analytics/dependency-graph",
          { files: payload, layout: "hierarchical" }
        );
      } catch { return null; }
    },
    enabled: Boolean(selectedProjectId) && filesWithContent.length > 0 && activeTab === "graph",
  });

  // Compute complexity locally (no backend endpoint needed)
  const complexityFiles = useMemo(() => {
    return filesWithContent
      .filter((f) => f.content && f.language === "python")
      .map((f) => {
        const cc = estimateComplexity(f.content);
        const lines = f.content.split("\n").length;
        const mi = maintainabilityIndex(cc, lines);
        return {
          file: f.path,
          avg_cyclomatic: cc,
          max_cyclomatic: cc,
          maintainability_index: mi,
          grade: ccToGrade(cc),
          total_lines: lines,
        };
      })
      .sort((a, b) => b.max_cyclomatic - a.max_cyclomatic);
  }, [filesWithContent]);

  // Include ALL language files for hotspot (not just python)
  const hotspotData = useMemo(() => {
    return filesWithContent
      .filter((f) => f.content)
      .map((f) => {
        const cc = estimateComplexity(f.content);
        const lines = f.content.split("\n").length;
        return {
          file: f.path,
          lines,
          complexity: cc,
          language: f.language,
        };
      })
      .sort((a, b) => b.complexity - a.complexity);
  }, [filesWithContent]);

  const languageBreakdown = useMemo(() =>
    files.reduce((acc, f) => {
      const lang = f.language || "unknown";
      acc[lang] = (acc[lang] || 0) + 1;
      return acc;
    }, {} as Record<string, number>),
    [files]
  );

  const languageData = Object.entries(languageBreakdown).map(([language, count]) => ({
    language,
    count,
  }));

  const avgCC = complexityFiles.length > 0
    ? (complexityFiles.reduce((s, f) => s + f.avg_cyclomatic, 0) / complexityFiles.length).toFixed(1)
    : "N/A";

  const TABS: { id: AnalyticsTab; label: string; icon: string }[] = [
    { id: "graph",      label: "Dependencies", icon: "🕸️" },
    { id: "complexity", label: "Complexity",   icon: "📊" },
    { id: "languages",  label: "Languages",    icon: "💻" },
    { id: "hotspots",   label: "Hotspots",     icon: "🔥" },
  ];

  const isLoading = filesLoading || contentsLoading;

  return (
    <div className="p-6 h-full flex flex-col">
      <div className="flex-shrink-0 flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">Analytics</h1>
          <p className="text-sm text-[var(--text-secondary)] mt-1">
            Code metrics, dependencies, and quality insights
          </p>
        </div>
        <select
          value={selectedProjectId ?? ""}
          onChange={(e) => setSelectedProjectId(e.target.value || null)}
          className="px-3 py-2 rounded-lg text-sm bg-[var(--bg-tertiary)] text-[var(--text-primary)] border border-[var(--border)] focus:border-[var(--border-focus)] focus:outline-none"
        >
          <option value="">Select a project</option>
          {projects.map((p: Project) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      {selectedProjectId && (
        <div className="flex-shrink-0 flex gap-1 mb-4 p-1 bg-[var(--bg-tertiary)] rounded-lg w-fit">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={[
                "px-3 py-1.5 text-xs font-medium rounded-md transition-colors",
                activeTab === tab.id
                  ? "bg-[var(--bg-primary)] text-[var(--text-primary)] shadow-sm"
                  : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]",
              ].join(" ")}
            >
              {tab.icon} {tab.label}
            </button>
          ))}
        </div>
      )}

      {selectedProjectId && !isLoading && files.length > 0 && (
        <div className="flex-shrink-0 flex gap-3 mb-4 flex-wrap">
          <Badge variant="info">📁 {files.length} files</Badge>
          <Badge variant="default">💻 {Object.keys(languageBreakdown).length} languages</Badge>
          {complexityFiles.length > 0 && (
            <Badge variant="default">📊 Avg CC: {avgCC}</Badge>
          )}
          {Boolean(graphData?.metadata) && (
            <Badge variant="default">🔗 {(graphData.metadata as { total_edges: number }).total_edges} deps</Badge>
          )}
        </div>
      )}

      <div className="flex-1 min-h-0 rounded-lg overflow-hidden border border-[var(--border)]">
        {!selectedProjectId ? (
          <div className="h-full flex flex-col items-center justify-center bg-[var(--bg-secondary)]">
            <div className="text-4xl mb-3">📊</div>
            <p className="text-sm text-[var(--text-muted)]">Select a project to view analytics</p>
          </div>
        ) : isLoading ? (
          <div className="h-full flex items-center justify-center bg-[var(--bg-secondary)]">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
              <p className="text-sm text-[var(--text-muted)]">Loading analytics...</p>
            </div>
          </div>
        ) : activeTab === "graph" ? (
          graphLoading ? (
            <div className="h-full flex items-center justify-center bg-[var(--bg-secondary)]">
              <div className="w-8 h-8 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
            </div>
          ) : graphData && (graphData.nodes as unknown[]).length > 0 ? (
            <DependencyGraph
              nodes={graphData.nodes as never}
              edges={graphData.edges as never}
              metadata={graphData.metadata as never}
            />
          ) : (
            <DependencyGraphEmpty />
          )
        ) : activeTab === "complexity" ? (
          <div className="h-full bg-[var(--bg-secondary)] p-4">
            {complexityFiles.length > 0 ? (
              <ComplexityChart data={complexityFiles} metric="max_cyclomatic" />
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <div className="text-3xl mb-2">📊</div>
                <p className="text-sm text-[var(--text-muted)]">
                  No complexity data — upload Python/JS files
                </p>
              </div>
            )}
          </div>
        ) : activeTab === "languages" ? (
          <div className="h-full bg-[var(--bg-secondary)] p-4">
            <LanguagePieChart data={languageData} />
          </div>
        ) : activeTab === "hotspots" ? (
          <div className="h-full bg-[var(--bg-secondary)] p-4 overflow-y-auto">
            {hotspotData.length > 0 ? (
              <HotspotMap data={hotspotData} />
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <div className="text-3xl mb-2">🔥</div>
                <p className="text-sm text-[var(--text-muted)]">
                  No hotspot data — upload source files first
                </p>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}