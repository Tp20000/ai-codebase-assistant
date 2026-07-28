/**
 * Upload Service - Step 44
 * AI Codebase Assistant v2.0
 *
 * Handles file upload to the backend with progress tracking.
 * Supports: individual files, multiple files, ZIP archives.
 */

import { apiClient } from "@/services/api";
import { UPLOAD_LIMITS } from "@/utils/constants";

export interface UploadedFile {
  id: string;
  file_path: string;
  language: string;
  size_bytes: number;
  line_count: number;
  is_binary: boolean;
}

export interface UploadResult {
  project_id: string;
  uploaded_count: number;
  skipped_count: number;
  failed_count: number;
  files: UploadedFile[];
  errors: string[];
}

export interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
  fileName: string;
  status: "uploading" | "processing" | "done" | "error";
}

export type ProgressCallback = (progress: UploadProgress) => void;

/**
 * Validate a file before upload.
 * Returns null if valid, error message string if invalid.
 */
export function validateFile(file: File): string | null {
  const maxSizeBytes = UPLOAD_LIMITS.MAX_FILE_SIZE_BYTES;
  const allowedExts = UPLOAD_LIMITS.ALLOWED_EXTENSIONS as readonly string[];

  if (file.size > maxSizeBytes) {
    return `File too large: ${(file.size / 1024 / 1024).toFixed(1)}MB (max ${UPLOAD_LIMITS.MAX_FILE_SIZE_MB}MB)`;
  }

  const ext = "." + file.name.split(".").pop()?.toLowerCase();
  const isZip = ext === ".zip";
  const isAllowed = allowedExts.includes(ext) || isZip;

  if (!isAllowed) {
    return `File type not supported: ${ext}`;
  }

  return null;
}

/**
 * Upload a single file to a project.
 */
export async function uploadFile(
  projectId: string,
  file: File,
  onProgress?: ProgressCallback
): Promise<UploadedFile[]> {
  const formData = new FormData();
  formData.append("file", file);

  onProgress?.({
    loaded: 0,
    total: file.size,
    percentage: 0,
    fileName: file.name,
    status: "uploading",
  });

  const response = await apiClient.post<UploadedFile[] | UploadResult>(
    `/projects/${projectId}/files/upload`,
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (event) => {
        const total = event.total ?? file.size;
        const loaded = event.loaded ?? 0;
        onProgress?.({
          loaded,
          total,
          percentage: Math.round((loaded / total) * 100),
          fileName: file.name,
          status: loaded >= total ? "processing" : "uploading",
        });
      },
    }
  );

  onProgress?.({
    loaded: file.size,
    total: file.size,
    percentage: 100,
    fileName: file.name,
    status: "done",
  });

  const data = response.data;
  if (Array.isArray(data)) return data;
  return (data as UploadResult).files ?? [];
}

/**
 * Upload multiple files sequentially with combined progress.
 */
export async function uploadMultipleFiles(
  projectId: string,
  files: File[],
  onProgress?: ProgressCallback
): Promise<UploadedFile[]> {
  const allUploaded: UploadedFile[] = [];

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    const baseProgress = Math.round((i / files.length) * 100);

    const uploaded = await uploadFile(projectId, file, (progress) => {
      const combinedPct = baseProgress + Math.round(progress.percentage / files.length);
      onProgress?.({
        ...progress,
        percentage: Math.min(99, combinedPct),
        fileName: `${file.name} (${i + 1}/${files.length})`,
      });
    });

    allUploaded.push(...uploaded);
  }

  return allUploaded;
}

/**
 * Upload a ZIP file — backend extracts and indexes all files inside.
 */
export async function uploadZip(
  projectId: string,
  zipFile: File,
  onProgress?: ProgressCallback
): Promise<UploadResult> {
  const formData = new FormData();
  formData.append("file", zipFile);

  onProgress?.({
    loaded: 0,
    total: zipFile.size,
    percentage: 0,
    fileName: zipFile.name,
    status: "uploading",
  });

  const response = await apiClient.post<UploadResult>(
    `/projects/${projectId}/files/upload-zip`,
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 300000, // 5 minutes for large ZIPs
      onUploadProgress: (event) => {
        const total = event.total ?? zipFile.size;
        const loaded = event.loaded ?? 0;
        const pct = Math.round((loaded / total) * 90); // cap at 90% (server processes after)
        onProgress?.({
          loaded,
          total,
          percentage: pct,
          fileName: zipFile.name,
          status: pct < 90 ? "uploading" : "processing",
        });
      },
    }
  );

  onProgress?.({
    loaded: zipFile.size,
    total: zipFile.size,
    percentage: 100,
    fileName: zipFile.name,
    status: "done",
  });

  return response.data;
}

/**
 * Get a human-readable file size string.
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

/**
 * Check if a file is a ZIP archive.
 */
export function isZipFile(file: File): boolean {
  return (
    file.type === "application/zip" ||
    file.type === "application/x-zip-compressed" ||
    file.name.toLowerCase().endsWith(".zip")
  );
}

/**
 * Get file extension from filename.
 */
export function getFileExtension(name: string): string {
  return "." + (name.split(".").pop()?.toLowerCase() ?? "");
}