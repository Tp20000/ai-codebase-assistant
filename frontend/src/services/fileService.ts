/**
 * File Service - Step 43/45 fix
 * AI Codebase Assistant v2.0
 */

import { apiGet } from "@/services/api";

export interface ProjectFileInfo {
  id: string;
  project_id: string;
  file_path: string;
  language: string;
  size_bytes: number;
  line_count: number;
  is_binary: boolean;
  is_parsed: boolean;
  is_embedded?: boolean;
  content_hash?: string | null;
  content?: string;
  created_at: string;
}

export interface FileTreeNode {
  name: string;
  path: string;
  type: "file" | "directory";
  language?: string;
  size?: number;
  children?: FileTreeNode[];
}

/**
 * Fetch all files for a project.
 */
export async function fetchProjectFiles(
  projectId: string,
  limit = 500
): Promise<ProjectFileInfo[]> {
  try {
    const result = await apiGet<ProjectFileInfo[] | { items: ProjectFileInfo[] }>(
      `/projects/${projectId}/files/`,
      { limit }
    );
    if (Array.isArray(result)) return result;
    return (result as { items: ProjectFileInfo[] }).items ?? [];
  } catch {
    return [];
  }
}

/**
 * Fetch content of a specific file.
 * Correct backend route: GET /projects/{project_id}/files/{file_id}
 */
export async function fetchFileContent(
  projectId: string,
  fileId: string
): Promise<string> {
  try {
    const result = await apiGet<ProjectFileInfo>(
      `/projects/${projectId}/files/${fileId}`
    );

    if (typeof result.content === "string" && result.content.length > 0) {
      return result.content;
    }

    return "// File content not available";
  } catch {
    return "// File content could not be loaded";
  }
}

/**
 * Build a file tree from flat file list.
 */
export function buildFileTree(files: ProjectFileInfo[]): FileTreeNode[] {
  const root: FileTreeNode[] = [];

  for (const file of files) {
    const parts = file.file_path.replace(/^\/+/, "").split("/");
    let currentLevel = root;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const currentPath = parts.slice(0, i + 1).join("/");
      const isLast = i === parts.length - 1;

      let node = currentLevel.find((n) => n.name === part);

      if (!node) {
        node = {
          name: part,
          path: currentPath,
          type: isLast ? "file" : "directory",
          ...(isLast
            ? {
                language: file.language,
                size: file.size_bytes,
              }
            : {
                children: [],
              }),
        };
        currentLevel.push(node);
      }

      if (!isLast) {
        if (!node.children) node.children = [];
        currentLevel = node.children;
      }
    }
  }

  const sortNodes = (nodes: FileTreeNode[]) => {
    nodes.sort((a, b) => {
      if (a.type !== b.type) return a.type === "directory" ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    nodes.forEach((n) => n.children && sortNodes(n.children));
  };

  sortNodes(root);
  return root;
}

export function getFileIcon(fileName: string, type: "file" | "directory"): string {
  if (type === "directory") return "📁";

  const ext = fileName.split(".").pop()?.toLowerCase() ?? "";
  const icons: Record<string, string> = {
    py: "🐍", js: "📜", jsx: "⚛️", ts: "🔷", tsx: "⚛️",
    java: "☕", go: "🐹", rs: "🦀", cpp: "⚡", c: "⚡",
    cs: "🟣", rb: "💎", php: "🐘", swift: "🧡", kt: "🎯",
    md: "📝", json: "🔧", yaml: "🔧", yml: "🔧", toml: "🔧",
    html: "🌐", css: "🎨", scss: "🎨", sql: "🗄️",
    sh: "💻", txt: "📄",
  };
  return icons[ext] ?? "📄";
}

export function getMonacoLanguage(fileName: string): string {
  const ext = fileName.split(".").pop()?.toLowerCase() ?? "";
  const langs: Record<string, string> = {
    py: "python", js: "javascript", jsx: "javascript",
    ts: "typescript", tsx: "typescript", java: "java",
    go: "go", rs: "rust", cpp: "cpp", c: "c",
    cs: "csharp", rb: "ruby", php: "php", swift: "swift",
    kt: "kotlin", md: "markdown", json: "json",
    yaml: "yaml", yml: "yaml", html: "html",
    css: "css", scss: "scss", sql: "sql", sh: "shell",
  };
  return langs[ext] ?? "plaintext";
}