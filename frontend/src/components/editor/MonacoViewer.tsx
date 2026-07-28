/**
 * Monaco Editor Viewer - Step 46
 * AI Codebase Assistant v2.0
 *
 * Read-only VS Code-like editor for viewing source files.
 *
 * Features:
 *   - Syntax highlighting for 20+ languages
 *   - Line numbers and minimap
 *   - Find (Ctrl+F) built-in
 *   - Highlight specific line ranges (from AI sources)
 *   - Dark/light theme sync with app theme
 *   - Loading skeleton while Monaco initializes
 *   - Error boundary for Monaco load failures
 *   - Keyboard shortcuts preserved (navigate, select, copy)
 */

import { useRef, useEffect, useState, useCallback } from "react";
import Editor, { type OnMount, type Monaco } from "@monaco-editor/react";
// monaco-editor types provided by @monaco-editor/react
import { useUIStore } from "@/stores/uiStore";
import { Skeleton } from "@/components/ui/Skeleton";
import { getMonacoLanguage } from "@/services/fileService";

// ── Types ─────────────────────────────────────────────────────────

interface HighlightRange {
  /** Start line (1-based) */
  startLine: number;
  /** End line (1-based, inclusive) */
  endLine: number;
  /** Highlight color variant */
  type?: "info" | "warning" | "error" | "success";
}

interface MonacoViewerProps {
  /** Source code content to display */
  content: string;
  /** File name (used for language detection) */
  fileName: string;
  /** Optional line ranges to highlight (e.g. from AI source citations) */
  highlights?: HighlightRange[];
  /** Jump to this line on load */
  scrollToLine?: number;
  /** Height of the editor (default: 100%) */
  height?: string;
  /** Called when user clicks a line number */
  onLineClick?: (line: number) => void;
  /** Additional CSS class */
  className?: string;
}

// ── Theme definitions ─────────────────────────────────────────────

const DARK_THEME_ID = "aca-dark";
const LIGHT_THEME_ID = "aca-light";

function defineThemes(monaco: Monaco) {
  monaco.editor.defineTheme(DARK_THEME_ID, {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "comment",    foreground: "6A9955", fontStyle: "italic" },
      { token: "keyword",    foreground: "569CD6" },
      { token: "string",     foreground: "CE9178" },
      { token: "number",     foreground: "B5CEA8" },
      { token: "type",       foreground: "4EC9B0" },
      { token: "class-name", foreground: "4EC9B0" },
      { token: "function",   foreground: "DCDCAA" },
    ],
    colors: {
      "editor.background":              "#0d1117",
      "editor.foreground":              "#e6edf3",
      "editor.lineHighlightBackground": "#161b22",
      "editor.selectionBackground":     "#264f78",
      "editorLineNumber.foreground":    "#484f58",
      "editorLineNumber.activeForeground": "#e6edf3",
      "editorCursor.foreground":        "#58a6ff",
      "editor.findMatchBackground":     "#f6f8fa20",
      "editor.findMatchHighlightBackground": "#f6f8fa10",
      "editorGutter.background":        "#0d1117",
      "minimap.background":             "#0d1117",
      "scrollbar.shadow":               "#00000000",
      "editorWidget.background":        "#161b22",
      "editorWidget.border":            "#30363d",
      "input.background":               "#21262d",
      "input.border":                   "#30363d",
      "input.foreground":               "#e6edf3",
    },
  });

  monaco.editor.defineTheme(LIGHT_THEME_ID, {
    base: "vs",
    inherit: true,
    rules: [],
    colors: {
      "editor.background":              "#ffffff",
      "editor.foreground":              "#1f2328",
      "editor.lineHighlightBackground": "#f6f8fa",
      "editorLineNumber.foreground":    "#8c959f",
      "editorGutter.background":        "#f6f8fa",
      "minimap.background":             "#f6f8fa",
    },
  });
}

// ── Highlight color map ───────────────────────────────────────────

const HIGHLIGHT_COLORS: Record<
  NonNullable<HighlightRange["type"]>,
  { background: string; border: string }
> = {
  info:    { background: "#3B82F620", border: "#3B82F6" },
  warning: { background: "#F59E0B20", border: "#F59E0B" },
  error:   { background: "#EF444420", border: "#EF4444" },
  success: { background: "#10B98120", border: "#10B981" },
};

// ── Main Component ────────────────────────────────────────────────

/**
 * Read-only Monaco editor for viewing source files.
 *
 * @example
 * <MonacoViewer
 *   content={fileContent}
 *   fileName="main.py"
 *   highlights={[{ startLine: 10, endLine: 15, type: "info" }]}
 *   scrollToLine={10}
 * />
 */
export function MonacoViewer({
  content,
  fileName,
  highlights = [],
  scrollToLine,
  height = "100%",
  onLineClick,
  className,
}: MonacoViewerProps) {
  const { theme } = useUIStore();
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<Monaco | null>(null);
  const decorationsRef = useRef<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const language = getMonacoLanguage(fileName);
  const monacoTheme = theme === "dark" ? DARK_THEME_ID : LIGHT_THEME_ID;

  // Apply decorations (line highlights) when highlights change
  const applyDecorations = useCallback(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco || highlights.length === 0) return;

    const newDecorations: editor.IModelDeltaDecoration[] = highlights.map(
      (h) => {
        const color = HIGHLIGHT_COLORS[h.type ?? "info"];
        return {
          range: new monaco.Range(h.startLine, 1, h.endLine, 9999),
          options: {
            isWholeLine: true,
            className: undefined,
            inlineClassName: undefined,
            glyphMarginClassName: undefined,
            lineNumberClassName: undefined,
            overviewRuler: {
              color: color.border,
              darkColor: color.border,
              position: monaco.editor.OverviewRulerLane.Left,
            },
          },
        };
      }
    );

    // Use the CSS approach via inline styles since Monaco custom decorations
    // work via CSS classes
    decorationsRef.current = editor.deltaDecorations(
      decorationsRef.current,
      highlights.map((h) => ({
        range: new monaco.Range(h.startLine, 1, h.endLine, 9999),
        options: {
          isWholeLine: true,
          className: `highlight-${h.type ?? "info"}`,
          overviewRuler: {
            color: HIGHLIGHT_COLORS[h.type ?? "info"].border,
            darkColor: HIGHLIGHT_COLORS[h.type ?? "info"].border,
            position: monaco.editor.OverviewRulerLane.Left,
          },
        },
      }))
    );
  }, [highlights]);

  // Scroll to a specific line
  const scrollToLineNumber = useCallback((line: number) => {
    const editor = editorRef.current;
    if (!editor || line <= 0) return;
    editor.revealLineInCenter(line);
    editor.setPosition({ lineNumber: line, column: 1 });
  }, []);

  // Monaco mount handler
  const handleMount: OnMount = useCallback(
    (editor, monaco) => {
      editorRef.current = editor;
      monacoRef.current = monaco;
      setIsLoading(false);

      // Define custom themes
      defineThemes(monaco);
      monaco.editor.setTheme(monacoTheme);

      // Apply initial decorations
      applyDecorations();

      // Scroll to initial line
      if (scrollToLine) {
        scrollToLineNumber(scrollToLine);
      }

      // Click handler for line numbers
      if (onLineClick) {
        editor.onMouseDown((e: unknown) => {
          const line = e.target.position?.lineNumber;
          if (line) onLineClick(line);
        });
      }

      // Add CSS for highlight classes
      const style = document.createElement("style");
      style.textContent = `
        .highlight-info    { background: ${HIGHLIGHT_COLORS.info.background} !important; border-left: 3px solid ${HIGHLIGHT_COLORS.info.border}; }
        .highlight-warning { background: ${HIGHLIGHT_COLORS.warning.background} !important; border-left: 3px solid ${HIGHLIGHT_COLORS.warning.border}; }
        .highlight-error   { background: ${HIGHLIGHT_COLORS.error.background} !important; border-left: 3px solid ${HIGHLIGHT_COLORS.error.border}; }
        .highlight-success { background: ${HIGHLIGHT_COLORS.success.background} !important; border-left: 3px solid ${HIGHLIGHT_COLORS.success.border}; }
      `;
      document.head.appendChild(style);
    },
    [monacoTheme, applyDecorations, scrollToLine, scrollToLineNumber, onLineClick]
  );

  // Update theme when app theme changes
  useEffect(() => {
    if (monacoRef.current) {
      monacoRef.current.editor.setTheme(monacoTheme);
    }
  }, [monacoTheme]);

  // Re-apply decorations when highlights change
  useEffect(() => {
    applyDecorations();
  }, [applyDecorations]);

  // Scroll when scrollToLine changes
  useEffect(() => {
    if (scrollToLine) {
      scrollToLineNumber(scrollToLine);
    }
  }, [scrollToLine, scrollToLineNumber]);

  // Error handler
  const handleError = useCallback(() => {
    setLoadError("Monaco editor failed to load. Showing plain text.");
    setIsLoading(false);
  }, []);

  // Fallback: plain text if Monaco fails
  if (loadError) {
    return (
      <div className={`h-full overflow-auto bg-[var(--bg-primary)] ${className ?? ""}`}>
        <pre className="text-xs font-mono p-4 text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap break-all">
          {content || "// No content"}
        </pre>
      </div>
    );
  }

  return (
    <div className={`relative h-full min-h-0 w-full ${className ?? ""}`} style={{ height, width: "100%" }}>
      {/* Loading skeleton */}
      {isLoading && (
        <div className="absolute inset-0 bg-[var(--bg-primary)] p-4 space-y-2 z-10">
          {Array.from({ length: 20 }).map((_, i) => (
            <Skeleton
              key={i}
              className="h-4"
              
            />
          ))}
        </div>
      )}

      {/* Monaco Editor */}
      <Editor
        width="100%"
        height={height}
        language={language}
        value={content || ""}
        theme={monacoTheme}
        onMount={handleMount}
        loading={null}
        options={{
          readOnly: true,
          minimap: { enabled: true, scale: 1 },
          lineNumbers: "on",
          lineNumbersMinChars: 4,
          folding: true,
          foldingHighlight: true,
          wordWrap: "off",
          scrollBeyondLastLine: false,
          fontSize: 13,
          fontFamily: '"JetBrains Mono", "Fira Code", monospace',
          fontLigatures: true,
          renderLineHighlight: "line",
          selectOnLineNumbers: true,
          cursorStyle: "line",
          automaticLayout: true,
          contextmenu: true,
          smoothScrolling: true,
          mouseWheelZoom: true,
          find: {
            addExtraSpaceOnTop: false,
            autoFindInSelection: "never",
            seedSearchStringFromSelection: "selection",
          },
          scrollbar: {
            vertical: "visible",
            horizontal: "visible",
            verticalScrollbarSize: 8,
            horizontalScrollbarSize: 8,
          },
          overviewRulerLanes: 3,
          padding: { top: 8, bottom: 8 },
          renderWhitespace: "selection",
          bracketPairColorization: { enabled: true },
          guides: {
            bracketPairs: true,
            indentation: true,
          },
        }}
      />
    </div>
  );
}