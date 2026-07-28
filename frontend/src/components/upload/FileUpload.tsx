/**
 * File Upload Component - Step 44
 * AI Codebase Assistant v2.0
 *
 * Features:
 *   - Drag-and-drop zone (files and ZIP archives)
 *   - Click to browse file picker
 *   - File list preview with size and type icons
 *   - ZIP detection with special handling note
 *   - Real-time upload progress bar
 *   - File validation (type + size)
 *   - Error display in UI (never console-only)
 *   - Auto-trigger indexing after upload completes
 */

import { useState, useRef, useCallback, type DragEvent, type ChangeEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { clsx } from "clsx";
import toast from "react-hot-toast";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/Button";
import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { UploadProgressBar } from "@/components/upload/UploadProgress";
import {
  uploadFile,
  uploadMultipleFiles,
  uploadZip,
  validateFile,
  formatFileSize,
  isZipFile,
  getFileExtension,
  type UploadProgress,
  type UploadedFile,
} from "@/services/uploadService";
import { UPLOAD_LIMITS } from "@/utils/constants";

// ── File Preview Item ─────────────────────────────────────────────

interface FilePreviewItemProps {
  file: File;
  onRemove: () => void;
}

function FilePreviewItem({ file, onRemove }: FilePreviewItemProps) {
  const ext = getFileExtension(file.name);
  const isZip = isZipFile(file);

  const extIcons: Record<string, string> = {
    ".py": "🐍", ".js": "📜", ".ts": "🔷", ".tsx": "⚛️", ".jsx": "⚛️",
    ".java": "☕", ".go": "🐹", ".rs": "🦀", ".cpp": "⚡", ".cs": "🟣",
    ".zip": "📦", ".md": "📝", ".json": "🔧", ".yaml": "🔧", ".yml": "🔧",
  };
  const icon = extIcons[ext] ?? "📄";

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -8 }}
      className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border)]"
    >
      <span className="text-base flex-shrink-0">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-[var(--text-primary)] truncate">
          {file.name}
        </p>
        <p className="text-[10px] text-[var(--text-muted)]">
          {formatFileSize(file.size)}
          {isZip && " · ZIP archive (all files will be extracted)"}
        </p>
      </div>
      <button
        onClick={onRemove}
        className="flex-shrink-0 w-5 h-5 rounded flex items-center justify-center text-[var(--text-muted)] hover:text-red-400 hover:bg-red-500/10 transition-colors text-xs"
        aria-label={`Remove ${file.name}`}
      >
        ×
      </button>
    </motion.div>
  );
}

// ── Main FileUpload Component ─────────────────────────────────────

interface FileUploadProps {
  /** Target project ID */
  projectId: string;
  /** Called when upload successfully completes */
  onUploadComplete?: (files: UploadedFile[]) => void;
  /** Called when modal/panel should close */
  onClose?: () => void;
}

/**
 * Drag-and-drop file uploader with progress tracking.
 *
 * States:
 *   idle      — drop zone + browse button
 *   files     — file list preview + upload button
 *   uploading — progress bar + cancel option
 *   done      — success summary + close button
 *   error     — visible error banner + retry option
 */
export function FileUpload({ projectId, onUploadComplete, onClose }: FileUploadProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadDone, setUploadDone] = useState(false);
  const [uploadedCount, setUploadedCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  // ── Drag handlers ───────────────────────────────────────────────

  const handleDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback((e: DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    setError(null);

    const droppedFiles = Array.from(e.dataTransfer.files);
    addFiles(droppedFiles);
  }, []);

  // ── File validation + adding ────────────────────────────────────

  const addFiles = useCallback((newFiles: File[]) => {
    const errors: string[] = [];
    const valid: File[] = [];

    for (const file of newFiles) {
      const err = validateFile(file);
      if (err) {
        errors.push(`${file.name}: ${err}`);
      } else {
        valid.push(file);
      }
    }

    if (errors.length > 0) {
      setError(errors.join("\n"));
    }

    if (valid.length > 0) {
      setFiles((prev) => {
        // Deduplicate by name
        const names = new Set(prev.map((f) => f.name));
        const unique = valid.filter((f) => !names.has(f.name));
        return [...prev, ...unique];
      });
    }
  }, []);

  const handleInputChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files ?? []);
    addFiles(selected);
    // Reset input so same file can be re-selected
    e.target.value = "";
  }, [addFiles]);

  const removeFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
    setError(null);
  }, []);

  // ── Upload handler ──────────────────────────────────────────────

  const handleUpload = useCallback(async () => {
    if (files.length === 0) return;

    setIsUploading(true);
    setError(null);
    setUploadDone(false);

    try {
      let uploaded: UploadedFile[] = [];

      if (files.length === 1 && isZipFile(files[0])) {
        // ZIP upload
        setProgress({
          loaded: 0,
          total: files[0].size,
          percentage: 0,
          fileName: files[0].name,
          status: "uploading",
        });

        const result = await uploadZip(projectId, files[0], (prog) => {
          setProgress(prog);
        });

        uploaded = result.files ?? [];
        setUploadedCount(result.uploaded_count ?? uploaded.length);

        if (result.errors?.length > 0) {
          toast(`${result.errors.length} files skipped during ZIP extraction`, {
            icon: "⚠️",
          });
        }
      } else {
        // Individual files
        uploaded = await uploadMultipleFiles(
          projectId,
          files,
          (prog) => setProgress(prog)
        );
        setUploadedCount(uploaded.length);
      }

      // Success!
      setUploadDone(true);
      setProgress({
        loaded: 1,
        total: 1,
        percentage: 100,
        fileName: files.length === 1 ? files[0].name : `${files.length} files`,
        status: "done",
      });

      // Invalidate file list cache so workspace refreshes
      queryClient.invalidateQueries({ queryKey: ["project-files", projectId] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });

      toast.success(
        `Uploaded ${uploaded.length} file${uploaded.length !== 1 ? "s" : ""} successfully!`
      );

      onUploadComplete?.(uploaded);

    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed";
      setError(message);
      setProgress((prev) => prev ? { ...prev, status: "error" } : null);
      toast.error("Upload failed — see error details");
    } finally {
      setIsUploading(false);
    }
  }, [files, projectId, queryClient, onUploadComplete]);

  // ── Reset ───────────────────────────────────────────────────────

  const handleReset = useCallback(() => {
    setFiles([]);
    setProgress(null);
    setUploadDone(false);
    setError(null);
  }, []);

  // ── Render ──────────────────────────────────────────────────────

  const hasFiles = files.length > 0;
  const hasZip = files.some(isZipFile);

  return (
    <div className="flex flex-col gap-4">
      {/* Error banner — always visible in UI */}
      <ErrorBanner
        message={error}
        onDismiss={() => setError(null)}
      />

      {/* Done state */}
      {uploadDone ? (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="text-center py-8"
        >
          <div className="text-4xl mb-3">✅</div>
          <h3 className="text-base font-semibold text-[var(--text-primary)] mb-1">
            Upload Complete!
          </h3>
          <p className="text-sm text-[var(--text-secondary)] mb-6">
            {uploadedCount} file{uploadedCount !== 1 ? "s" : ""} uploaded successfully.
            <br />
            Your project is ready for indexing and analysis.
          </p>
          <div className="flex gap-3 justify-center">
            <Button variant="secondary" onClick={handleReset}>
              Upload More
            </Button>
            <Button variant="primary" onClick={onClose}>
              Done
            </Button>
          </div>
        </motion.div>
      ) : (
        <>
          {/* Drop zone */}
          {!isUploading && (
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => !hasFiles && inputRef.current?.click()}
              className={clsx(
                "border-2 border-dashed rounded-xl p-8 text-center transition-all duration-150",
                isDragOver
                  ? "border-blue-400 bg-blue-500/10 scale-[1.01]"
                  : hasFiles
                  ? "border-[var(--border)] bg-[var(--bg-tertiary)]"
                  : "border-[var(--border)] hover:border-blue-400/50 hover:bg-[var(--bg-hover)] cursor-pointer",
              )}
            >
              {!hasFiles ? (
                <>
                  <div className="text-4xl mb-3">
                    {isDragOver ? "📂" : "📁"}
                  </div>
                  <p className="text-sm font-medium text-[var(--text-primary)] mb-1">
                    {isDragOver ? "Drop files here" : "Drop files or click to browse"}
                  </p>
                  <p className="text-xs text-[var(--text-muted)] mb-3">
                    Supports individual source files or a single ZIP archive
                  </p>
                  <div className="flex flex-wrap gap-1 justify-center">
                    {[".py", ".js", ".ts", ".java", ".go", ".rs", ".zip"].map((ext) => (
                      <span
                        key={ext}
                        className="px-1.5 py-0.5 rounded text-[10px] bg-[var(--bg-hover)] text-[var(--text-muted)] border border-[var(--border)]"
                      >
                        {ext}
                      </span>
                    ))}
                    <span className="px-1.5 py-0.5 rounded text-[10px] text-[var(--text-muted)]">
                      and more
                    </span>
                  </div>
                  <p className="text-[10px] text-[var(--text-muted)] mt-2">
                    Max {UPLOAD_LIMITS.MAX_FILE_SIZE_MB}MB per file
                  </p>
                </>
              ) : (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    inputRef.current?.click();
                  }}
                  className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
                >
                  + Add more files
                </button>
              )}

              <input
                ref={inputRef}
                type="file"
                multiple
                className="hidden"
                accept={[...UPLOAD_LIMITS.ALLOWED_EXTENSIONS, ".zip"].join(",")}
                onChange={handleInputChange}
              />
            </div>
          )}

          {/* Upload progress */}
          {isUploading && progress && (
            <div className="space-y-3">
              <p className="text-sm font-medium text-[var(--text-primary)]">
                Uploading...
              </p>
              <UploadProgressBar progress={progress} />
            </div>
          )}

          {/* File list */}
          {hasFiles && !isUploading && (
            <div className="space-y-2">
              <p className="text-xs text-[var(--text-muted)] uppercase tracking-wide">
                {files.length} file{files.length !== 1 ? "s" : ""} selected
                {hasZip && " · ZIP will be extracted automatically"}
              </p>
              <AnimatePresence>
                <div className="space-y-1.5 max-h-48 overflow-y-auto">
                  {files.map((file, i) => (
                    <FilePreviewItem
                      key={`${file.name}-${i}`}
                      file={file}
                      onRemove={() => removeFile(i)}
                    />
                  ))}
                </div>
              </AnimatePresence>
            </div>
          )}

          {/* Action buttons */}
          {hasFiles && !isUploading && (
            <div className="flex gap-3">
              <Button
                variant="secondary"
                onClick={handleReset}
                className="flex-shrink-0"
              >
                Clear
              </Button>
              <Button
                variant="primary"
                fullWidth
                onClick={handleUpload}
                isLoading={isUploading}
                leftIcon={<span>⬆</span>}
              >
                Upload {files.length} file{files.length !== 1 ? "s" : ""}
                {hasZip && " (ZIP)"}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── FileUpload Modal wrapper ──────────────────────────────────────

interface FileUploadModalProps {
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
  onUploadComplete?: (files: UploadedFile[]) => void;
}

/**
 * FileUpload wrapped in a modal dialog.
 * Used from the ProjectWorkspace header.
 */
export function FileUploadModal({
  projectId,
  isOpen,
  onClose,
  onUploadComplete,
}: FileUploadModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      {/* Modal */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 8 }}
        transition={{ duration: 0.15 }}
        className="relative w-full max-w-lg bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)]">
          <div>
            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              Upload Files
            </h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              Add source code files or a ZIP archive to this project
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-lg flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] transition-colors text-lg"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="p-5">
          <FileUpload
            projectId={projectId}
            onUploadComplete={onUploadComplete}
            onClose={onClose}
          />
        </div>
      </motion.div>
    </div>
  );
}