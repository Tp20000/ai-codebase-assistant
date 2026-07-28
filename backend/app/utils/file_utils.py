"""
File Utilities — Validation, detection, and extraction helpers.

Handles:
- Extension-based language detection
- File type validation (whitelist approach)
- ZIP archive extraction with path traversal protection
- File size validation
- Binary file detection
- Content hash computation (SHA-256)
"""

import hashlib
import io
import logging
import os
import zipfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Language Detection Map
# ─────────────────────────────────────────────

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py":    "python",
    ".pyw":   "python",
    ".pyi":   "python",
    ".js":    "javascript",
    ".mjs":   "javascript",
    ".cjs":   "javascript",
    ".jsx":   "javascript",
    ".ts":    "typescript",
    ".tsx":   "typescript",
    ".java":  "java",
    ".kt":    "kotlin",
    ".kts":   "kotlin",
    ".cpp":   "cpp",
    ".cc":    "cpp",
    ".cxx":   "cpp",
    ".c":     "c",
    ".h":     "c",
    ".hpp":   "cpp",
    ".go":    "go",
    ".rs":    "rust",
    ".rb":    "ruby",
    ".php":   "php",
    ".cs":    "csharp",
    ".swift": "swift",
    ".scala": "scala",
    ".r":     "r",
    ".R":     "r",
    ".sh":    "bash",
    ".bash":  "bash",
    ".zsh":   "bash",
    ".ps1":   "powershell",
    ".sql":   "sql",
    ".html":  "html",
    ".htm":   "html",
    ".css":   "css",
    ".scss":  "css",
    ".sass":  "css",
    ".less":  "css",
    ".json":  "json",
    ".yaml":  "yaml",
    ".yml":   "yaml",
    ".toml":  "toml",
    ".xml":   "xml",
    ".md":    "markdown",
    ".rst":   "rst",
    ".txt":   "text",
    ".env":   "text",
    ".gitignore": "text",
    ".dockerfile": "dockerfile",
}

# Files allowed for upload (source code + config)
ALLOWED_EXTENSIONS: set[str] = set(EXTENSION_TO_LANGUAGE.keys()) | {".zip"}

# Extensions to skip even if inside a ZIP (binary, compiled, etc.)
SKIP_EXTENSIONS: set[str] = {
    ".pyc", ".pyo", ".pyd",
    ".class", ".jar", ".war", ".ear",
    ".exe", ".dll", ".so", ".dylib", ".lib", ".a",
    ".o", ".obj",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".node_modules",
    ".git",
}

# Directories to skip when extracting ZIP
SKIP_DIRECTORIES: set[str] = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "env", ".env", "dist", "build", "target", ".idea",
    ".vscode", "vendor", "Pods", ".gradle",
}

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024   # 10MB per file
MAX_ZIP_SIZE_BYTES  = 100 * 1024 * 1024  # 100MB total ZIP
MAX_FILES_PER_ZIP   = 1000


def get_language(file_path: str) -> str:
    """
    Detect programming language from file extension.

    Args:
        file_path: File path or name with extension

    Returns:
        Language string (e.g. 'python', 'javascript')
        Returns 'unknown' for unrecognized extensions
    """
    ext = Path(file_path).suffix.lower()
    # Special case for Dockerfile
    name = Path(file_path).name.lower()
    if name in ("dockerfile", "containerfile"):
        return "dockerfile"
    if name == "makefile":
        return "makefile"
    return EXTENSION_TO_LANGUAGE.get(ext, "unknown")


def is_allowed_file(filename: str) -> bool:
    """
    Check if a file is allowed for upload based on extension.

    Args:
        filename: File name to check

    Returns:
        True if file extension is in the allowed set
    """
    ext = Path(filename).suffix.lower()
    name = Path(filename).name.lower()
    # Allow Dockerfile, Makefile explicitly
    if name in ("dockerfile", "containerfile", "makefile", "procfile"):
        return True
    return ext in ALLOWED_EXTENSIONS


def should_skip_file(file_path: str) -> bool:
    """
    Check if a file should be skipped during ZIP extraction.
    Skips binary files, compiled artifacts, and hidden system files.

    Args:
        file_path: Full path within the ZIP

    Returns:
        True if this file should be ignored
    """
    path = Path(file_path)

    # Check all parent directories
    for part in path.parts:
        if part in SKIP_DIRECTORIES:
            return True
        # Skip hidden directories (except .github, .env files)
        if part.startswith(".") and part not in (".github", ".gitignore", ".env.example"):
            return True

    # Check extension
    ext = path.suffix.lower()
    if ext in SKIP_EXTENSIONS:
        return True

    # Skip very long paths (likely generated)
    if len(str(file_path)) > 500:
        return True

    return False


def is_binary_file(content: bytes, sample_size: int = 8192) -> bool:
    """
    Detect if file content is binary by checking for null bytes.
    Uses the first sample_size bytes for efficiency.

    Args:
        content: File bytes to check
        sample_size: Number of bytes to sample

    Returns:
        True if file appears to be binary
    """
    sample = content[:sample_size]
    if b"\x00" in sample:
        return True
    # Check for high proportion of non-printable characters
    non_printable = sum(1 for byte in sample if byte < 9 or (14 <= byte <= 31))
    if len(sample) > 0 and non_printable / len(sample) > 0.30:
        return True
    return False


def compute_hash(content: bytes) -> str:
    """
    Compute SHA-256 hash of file content.
    Used for deduplication — don't re-index identical files.

    Args:
        content: File bytes

    Returns:
        Hex-encoded SHA-256 hash string
    """
    return hashlib.sha256(content).hexdigest()


def count_lines(content: bytes) -> int:
    """
    Count number of lines in file content.

    Args:
        content: File bytes (decoded as UTF-8 with error replacement)

    Returns:
        Line count
    """
    try:
        text = content.decode("utf-8", errors="replace")
        return text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    except Exception:
        return 0


def validate_zip_file(content: bytes) -> tuple[bool, str]:
    """
    Validate that bytes represent a valid ZIP archive.

    Args:
        content: ZIP file bytes

    Returns:
        Tuple of (is_valid, error_message)
        error_message is empty string if valid
    """
    if len(content) > MAX_ZIP_SIZE_BYTES:
        size_mb = len(content) / 1024 / 1024
        return False, f"ZIP file too large: {size_mb:.1f}MB (max {MAX_ZIP_SIZE_BYTES // 1024 // 1024}MB)"

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            # Check for zip bomb (compressed ratio)
            names = zf.namelist()
            if len(names) > MAX_FILES_PER_ZIP:
                return False, f"ZIP contains too many files: {len(names)} (max {MAX_FILES_PER_ZIP})"

            # Check for path traversal attacks
            for name in names:
                if name.startswith("/") or ".." in name:
                    return False, f"ZIP contains unsafe path: {name}"

        return True, ""
    except zipfile.BadZipFile:
        return False, "File is not a valid ZIP archive."
    except Exception as exc:
        return False, f"ZIP validation error: {exc}"


def extract_zip_files(
    content: bytes,
    max_file_size: int = MAX_FILE_SIZE_BYTES,
) -> list[dict]:
    """
    Extract source files from a ZIP archive.
    Skips binary files, compiled artifacts, and hidden directories.

    Args:
        content: ZIP file bytes
        max_file_size: Maximum size per extracted file in bytes

    Returns:
        List of file dictionaries with keys:
        - path: Relative path within ZIP
        - name: File name
        - content: File bytes
        - size_bytes: File size
        - language: Detected language
        - line_count: Number of lines
        - is_binary: Whether file appears binary
        - content_hash: SHA-256 hash
    """
    extracted: list[dict] = []

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        # Strip common root directory (e.g., repo-main/ prefix)
        all_names = [n for n in zf.namelist() if not n.endswith("/")]
        root_prefix = _detect_root_prefix(all_names)

        for zip_path in all_names:
            # Remove root prefix
            relative_path = zip_path[len(root_prefix):] if root_prefix else zip_path
            if not relative_path:
                continue

            # Skip files that should be ignored
            if should_skip_file(relative_path):
                logger.debug(f"Skipping: {relative_path}")
                continue

            # Check if file extension is allowed
            if not is_allowed_file(relative_path):
                logger.debug(f"Skipping (not allowed): {relative_path}")
                continue

            # Get file info
            try:
                info = zf.getinfo(zip_path)
                if info.file_size > max_file_size:
                    logger.warning(f"Skipping large file: {relative_path} ({info.file_size} bytes)")
                    continue

                file_content = zf.read(zip_path)
            except Exception as exc:
                logger.warning(f"Could not read {zip_path}: {exc}")
                continue

            # Check for binary
            binary = is_binary_file(file_content)

            extracted.append({
                "path": relative_path,
                "name": Path(relative_path).name,
                "content": file_content,
                "size_bytes": len(file_content),
                "language": get_language(relative_path),
                "line_count": count_lines(file_content) if not binary else 0,
                "is_binary": binary,
                "content_hash": compute_hash(file_content),
            })

    logger.info(f"Extracted {len(extracted)} files from ZIP")
    return extracted


def _detect_root_prefix(names: list[str]) -> str:
    """
    Detect and return common root prefix in ZIP (e.g., 'repo-main/').
    GitHub ZIP downloads wrap everything in a root directory.

    Args:
        names: List of file paths within ZIP

    Returns:
        Common prefix string (empty if no common prefix)
    """
    if not names:
        return ""

    # Find common prefix
    first_parts = [n.split("/")[0] for n in names if "/" in n]
    if not first_parts:
        return ""

    # If all files share the same root directory
    unique_roots = set(first_parts)
    if len(unique_roots) == 1:
        root = unique_roots.pop()
        # Verify it looks like a directory (more than 1 file under it)
        under_root = [n for n in names if n.startswith(f"{root}/")]
        if len(under_root) > 1:
            return f"{root}/"

    return ""