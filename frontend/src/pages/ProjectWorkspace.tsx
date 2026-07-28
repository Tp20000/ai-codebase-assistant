/**
 * Project Workspace - Clean rebuild
 * AI Codebase Assistant v2.0
 *
 * Three-pane layout:
 *   [File Tree] | [Monaco Code Viewer] | [AI Chat]
 */

import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";

import { ResizablePanel } from "@/components/layout/ResizablePanel";
import { MonacoViewer } from "@/components/editor/MonacoViewer";
import { FileUploadModal } from "@/components/upload/FileUpload";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { AgentPanel } from "@/components/agents/AgentPanel";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import {
  fetchProjectFiles,
  fetchFileContent,
  buildFileTree,
  getFileIcon,
  type FileTreeNode,
  type ProjectFileInfo,
} from "@/services/fileService";
import type { Project } from "@/services/projectService";
import { apiGet } from "@/services/api";

// ─────────────────────────────────────────────────────────────
// File Tree
// ─────────────────────────────────────────────────────────────

interface FileTreeItemProps {
  node: FileTreeNode;
  depth: number;
  selectedPath: string | null;
  onSelect: (node: FileTreeNode) => void;
}

function FileTreeItem({
  node,
  depth,
  selectedPath,
  onSelect,
}: FileTreeItemProps) {
  const [expanded, setExpanded] = useState(depth < 1);
  const isDir = node.type === "directory";
  const isSelected = node.path === selectedPath;

  return (
    <div>
      <button
        onClick={() => {
          if (isDir) setExpanded((v) => !v);
          else onSelect(node);
        }}
        className={[
          "w-full flex items-center gap-1.5 px-2 py-1 rounded text-left text-xs transition-colors",
          isSelected
            ? "bg-blue-500/20 text-blue-300"
            : "text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]",
        ].join(" ")}
        style={{ paddingLeft: `${8 + depth * 12}px` }}
        title={node.path}
      >
        {isDir ? (
          <span className="w-3 text-[10px] text-[var(--text-muted)]">
            {expanded ? "▼" : "▶"}
          </span>
        ) : (
          <span className="w-3" />
        )}

        <span className="text-sm flex-shrink-0">
          {getFileIcon(node.name, node.type)}
        </span>

        <span className="truncate">{node.name}</span>
      </button>

      {isDir && expanded && node.children && (
        <div>
          {node.children.map((child) => (
            <FileTreeItem
              key={child.path}
              node={child}
              depth={depth + 1}
              selectedPath={selectedPath}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface FileTreePanelProps {
  projectId: string;
  files: ProjectFileInfo[];
  isLoading: boolean;
  selectedPath: string | null;
  onFileSelect: (file: ProjectFileInfo) => void;
}

function FileTreePanel({
  projectId,
  files,
  isLoading,
  selectedPath,
  onFileSelect,
}: FileTreePanelProps) {
  const [search, setSearch] = useState("");
  const tree = buildFileTree(files);

  const filteredFiles = search
    ? files.filter((f) =>
        f.file_path.toLowerCase().includes(search.toLowerCase())
      )
    : null;

  const handleNodeSelect = useCallback(
    (node: FileTreeNode) => {
      if (node.type !== "file") return;
      const file = files.find(
        (f) => f.file_path === node.path || f.file_path.endsWith(node.path)
      );
      if (file) onFileSelect(file);
    },
    [files, onFileSelect]
  );

  return (
    <div className="h-full min-h-0 flex flex-col bg-[var(--bg-secondary)]">
      <div className="flex-shrink-0 px-3 py-2 border-b border-[var(--border)]">
        <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2">
          Files
        </p>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search files..."
          className="w-full px-2 py-1 text-xs rounded bg-[var(--bg-tertiary)] border border-[var(--border)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--border-focus)]"
        />
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto py-1">
        {isLoading ? (
          <div className="px-3 space-y-1 mt-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton
                key={i}
                className="h-4"
              />
            ))}
          </div>
        ) : files.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-xs text-[var(--text-muted)]">
              No files uploaded yet.
            </p>
            <p className="text-xs text-[var(--text-muted)] mt-1">
              Upload files to get started.
            </p>
          </div>
        ) : filteredFiles !== null ? (
          <div className="py-1">
            {filteredFiles.slice(0, 100).map((f) => (
              <button
                key={f.id}
                onClick={() => onFileSelect(f)}
                className={[
                  "w-full flex items-center gap-2 px-3 py-1 text-xs transition-colors text-left",
                  selectedPath === f.file_path
                    ? "bg-blue-500/20 text-blue-300"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-hover)]",
                ].join(" ")}
              >
                <span>{getFileIcon(f.file_path, "file")}</span>
                <span className="truncate">{f.file_path}</span>
              </button>
            ))}
            {filteredFiles.length === 0 && (
              <p className="text-xs text-[var(--text-muted)] px-3 py-2">
                No files match "{search}"
              </p>
            )}
          </div>
        ) : (
          <div className="py-1">
            {tree.map((node) => (
              <FileTreeItem
                key={node.path}
                node={node}
                depth={0}
                selectedPath={selectedPath}
                onSelect={handleNodeSelect}
              />
            ))}
          </div>
        )}
      </div>

      <div className="flex-shrink-0 px-3 py-1.5 border-t border-[var(--border)]">
        <p className="text-[10px] text-[var(--text-muted)]">
          {files.length} file{files.length !== 1 ? "s" : ""}
        </p>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Code Viewer
// ─────────────────────────────────────────────────────────────

interface OpenTab {
  file: ProjectFileInfo;
  content: string | null;
  isLoading: boolean;
}

interface CodeViewerProps {
  tabs: OpenTab[];
  activeTabId: string | null;
  onTabSelect: (id: string) => void;
  onTabClose: (id: string) => void;
}

function CodeViewer({
  tabs,
  activeTabId,
  onTabSelect,
  onTabClose,
}: CodeViewerProps) {
  const activeTab = tabs.find((t) => t.file.id === activeTabId);

  if (tabs.length === 0) {
    return (
      <div className="h-full min-h-0 flex flex-col items-center justify-center bg-[var(--bg-primary)]">
        <div className="text-4xl mb-4">📄</div>
        <p className="text-sm text-[var(--text-muted)]">
          Select a file from the tree to view it
        </p>
        <p className="text-xs text-[var(--text-muted)] mt-1">
          Or use the chat panel to ask about your code →
        </p>
      </div>
    );
  }

  return (
    <div className="h-full min-h-0 flex flex-col bg-[var(--bg-primary)]">
      {/* Tabs */}
      <div className="flex-shrink-0 flex items-center border-b border-[var(--border)] bg-[var(--bg-secondary)] overflow-x-auto">
        {tabs.map((tab) => {
          const isActive = tab.file.id === activeTabId;
          const fileName =
            tab.file.file_path.split("/").pop() ?? tab.file.file_path;

          return (
            <div
              key={tab.file.id}
              onClick={() => onTabSelect(tab.file.id)}
              className={[
                "flex items-center gap-2 px-3 py-2 text-xs cursor-pointer border-r border-[var(--border)] flex-shrink-0 group min-w-0 max-w-56 transition-colors",
                isActive
                  ? "bg-[var(--bg-primary)] text-[var(--text-primary)] border-t-2 border-t-blue-500"
                  : "text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-secondary)]",
              ].join(" ")}
            >
              <span>{getFileIcon(fileName, "file")}</span>
              <span className="truncate">{fileName}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onTabClose(tab.file.id);
                }}
                className="w-4 h-4 flex items-center justify-center rounded opacity-0 group-hover:opacity-100 hover:bg-[var(--bg-hover)]"
                aria-label="Close tab"
              >
                ×
              </button>
            </div>
          );
        })}
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {activeTab?.isLoading ? (
          <div className="p-4 space-y-2">
            {Array.from({ length: 20 }).map((_, i) => (
              <Skeleton
                key={i}
                className="h-4"
              />
            ))}
          </div>
        ) : (
          <div className="h-full min-h-0 w-full">
            <MonacoViewer
              content={activeTab?.content ?? ""}
              fileName={
                activeTab?.file.file_path.split("/").pop() ?? "file"
              }
              height="100%"
              className="h-full"
            />
          </div>
        )}
      </div>

      {/* Status bar */}
      {activeTab && (
        <div className="flex-shrink-0 flex items-center gap-4 px-3 py-1 border-t border-[var(--border)] bg-[var(--bg-tertiary)] text-[10px] text-[var(--text-muted)]">
          <span>{activeTab.file.file_path}</span>
          <span>{activeTab.file.line_count ?? 0} lines</span>
          <span>{activeTab.file.language ?? "unknown"}</span>
          <span className="ml-auto">
            {activeTab.file.size_bytes
              ? `${(activeTab.file.size_bytes / 1024).toFixed(1)} KB`
              : ""}
          </span>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Header
// ─────────────────────────────────────────────────────────────

function ProjectHeader({
  project,
  isLoading,
  fileCount,
  onBack,
  onUpload,
}: {
  project: Project | null;
  isLoading: boolean;
  fileCount: number;
  onBack: () => void;
  onUpload: () => void;
}) {
  if (isLoading) {
    return (
      <div className="flex items-center gap-3 px-4 h-11 border-b border-[var(--border)] bg-[var(--bg-secondary)]">
        <Skeleton className="h-4 w-4 rounded" />
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-5 w-16 rounded-full ml-2" />
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 px-4 h-11 border-b border-[var(--border)] bg-[var(--bg-secondary)] flex-shrink-0">
      <button
        onClick={onBack}
        className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors text-sm"
        title="Back to dashboard"
      >
        ←
      </button>

      <div className="w-px h-4 bg-[var(--border)]" />

      <span className="text-sm font-semibold text-[var(--text-primary)] truncate">
        {project?.name ?? "Project"}
      </span>

      {project?.language && (
        <Badge variant="info" className="text-[10px]">
          {project.language}
        </Badge>
      )}

      {project && (
        <Badge
          variant={project.indexed ? "success" : "warning"}
          dot
          className="text-[10px]"
        >
          {project.indexed ? "Indexed" : "Not indexed"}
        </Badge>
      )}

      <button
        onClick={onUpload}
        className="ml-auto mr-2 px-3 py-1.5 text-xs rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors flex items-center gap-1.5"
      >
        <span>⬆</span>
        <span>Upload Files</span>
      </button>

      <div className="flex items-center gap-3 text-[10px] text-[var(--text-muted)]">
        <span>📁 {fileCount} files</span>
        <span>
          <kbd className="px-1.5 py-0.5 rounded bg-[var(--bg-hover)] border border-[var(--border)] text-[9px]">
            Esc
          </kbd>{" "}
          close tab
        </span>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Main Workspace
// ─────────────────────────────────────────────────────────────

export default function ProjectWorkspace() {
  const { id: projectId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [showUploadModal, setShowUploadModal] = useState(false);
  const [rightTab, setRightTab] = useState<"chat" | "agents">("chat");
  const [openTabs, setOpenTabs] = useState<OpenTab[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);

  // Project metadata
  const { data: project, isLoading: projectLoading } = useQuery<Project>({
    queryKey: ["project", projectId],
    queryFn: async () => {
      try {
        return await apiGet<Project>(`/projects/${projectId}`);
      } catch {
        return {
          id: projectId ?? "",
          name: "Project",
          language: "unknown",
          indexed: false,
          file_count: 0,
          description: "",
          owner_id: "",
          created_at: "",
          updated_at: "",
        } as Project;
      }
    },
    enabled: Boolean(projectId),
    retry: 1,
  });

  // File list
  const {
    data: files = [],
    isLoading: filesLoading,
    isError,
    error,
    refetch,
  } = useQuery<ProjectFileInfo[]>({
    queryKey: ["project-files", projectId],
    queryFn: () => fetchProjectFiles(projectId!),
    enabled: Boolean(projectId),
    retry: 1,
  });

  // Escape closes current tab
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && activeTabId) {
        handleTabClose(activeTabId);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [activeTabId]);

  const handleFileSelect = useCallback(
    async (file: ProjectFileInfo) => {
      if (!projectId) return;
      setSelectedFilePath(file.file_path);

      const existing = openTabs.find((t) => t.file.id === file.id);
      if (existing) {
        setActiveTabId(file.id);
        return;
      }

      const newTab: OpenTab = {
        file,
        content: null,
        isLoading: true,
      };

      setOpenTabs((prev) => [...prev, newTab]);
      setActiveTabId(file.id);

      try {
        const content = await fetchFileContent(projectId, file.id);
        setOpenTabs((prev) =>
          prev.map((t) =>
            t.file.id === file.id
              ? { ...t, content, isLoading: false }
              : t
          )
        );
      } catch {
        setOpenTabs((prev) =>
          prev.map((t) =>
            t.file.id === file.id
              ? {
                  ...t,
                  content: "// File content could not be loaded",
                  isLoading: false,
                }
              : t
          )
        );
      }
    },
    [openTabs, projectId]
  );

  const handleTabSelect = useCallback(
    (id: string) => {
      setActiveTabId(id);
      const tab = openTabs.find((t) => t.file.id === id);
      if (tab) setSelectedFilePath(tab.file.file_path);
    },
    [openTabs]
  );

  const handleTabClose = useCallback(
    (id: string) => {
      setOpenTabs((prev) => {
        const remaining = prev.filter((t) => t.file.id !== id);
        if (activeTabId === id) {
          const nextTab = remaining[remaining.length - 1] ?? null;
          setActiveTabId(nextTab?.file.id ?? null);
          setSelectedFilePath(nextTab?.file.file_path ?? null);
        }
        return remaining;
      });
    },
    [activeTabId]
  );

  const activeFile =
    openTabs.find((t) => t.file.id === activeTabId)?.file ?? null;
  const activeTabContent =
    openTabs.find((t) => t.file.id === activeTabId)?.content ?? null;

  if (!projectId) {
    return (
      <div className="p-6">
        <ErrorBanner message="No project ID in URL" />
      </div>
    );
  }

  return (
    <div className="h-full min-h-0 flex flex-col overflow-hidden">
      <ProjectHeader
        project={project ?? null}
        isLoading={projectLoading}
        fileCount={files.length}
        onBack={() => navigate("/")}
        onUpload={() => setShowUploadModal(true)}
      />

      {isError && (
        <div className="p-4">
          <ErrorBanner
            title="Failed to load project files"
            message={(error as Error)?.message}
          />
        </div>
      )}

      <FileUploadModal
        projectId={projectId}
        isOpen={showUploadModal}
        onClose={() => setShowUploadModal(false)}
        onUploadComplete={() => {
          setShowUploadModal(false);
          refetch();
        }}
      />

      <div className="flex-1 min-h-0 overflow-hidden">
        <ResizablePanel
          className="h-full min-h-0"
          initialSize={220}
          minSize={160}
          maxSize={380}
          secondMinSize={640}
          first={
            <FileTreePanel
              projectId={projectId}
              files={files}
              isLoading={filesLoading}
              selectedPath={selectedFilePath}
              onFileSelect={handleFileSelect}
            />
          }
          second={
            <ResizablePanel
              className="h-full min-h-0"
              initialSize={420}
              minSize={260}
              maxSize={760}
              secondMinSize={320}
              first={
                <CodeViewer
                  tabs={openTabs}
                  activeTabId={activeTabId}
                  onTabSelect={handleTabSelect}
                  onTabClose={handleTabClose}
                />
              }
              second={
                <div className="h-full min-h-0 flex flex-col border-l border-[var(--border)]">
                  {/* Tab bar */}
                  <div className="flex-shrink-0 flex h-10 border-b border-[var(--border)] bg-[var(--bg-secondary)]">
                    {(["chat", "agents"] as const).map((tab) => (
                      <button
                        key={tab}
                        onClick={() => { console.log("TAB CLICKED:", tab); setRightTab(tab); }}
                        className={[
                          "flex-1 h-10 py-2 text-xs font-medium transition-colors capitalize flex items-center justify-center",
                          rightTab === tab
                            ? "text-[var(--text-primary)] border-b-2 border-blue-500"
                            : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]",
                        ].join(" ")}
                      >
                        {tab === "chat" ? "💬 Chat" : "🤖 Agents"}
                      </button>
                    ))}
                  </div>
                  {/* Tab content */}
                  <div className="flex-1 min-h-0 overflow-hidden">
                    {rightTab === "chat" ? (
                      <ChatWindow
                        projectId={projectId}
                        selectedFile={activeFile}
                        selectedFileContent={activeTabContent}
                      />
                    ) : (
                      <AgentPanel
                        projectId={projectId}
                        selectedFile={activeFile}
                        selectedFileContent={activeTabContent}
                      />
                    )}
                  </div>
                </div>
              }
            />
          }
        />
      </div>
    </div>
  );
}