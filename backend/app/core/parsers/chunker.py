"""
Smart Code Chunking Engine.

Goal:
  Split source code into semantically meaningful chunks for embedding and retrieval.

Chunking strategy:
  1. Imports block → one chunk
  2. Top-level functions → one chunk per function
  3. Classes → one chunk per class if small enough
  4. Large classes → split into class header + per-method chunks
  5. Remaining module-level logic → grouped into module chunks
  6. Oversized regions → split by sliding line windows with overlap

This engine intentionally favors semantic cohesion over strict size uniformity.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from app.core.parsers.code_parser import CodeParser

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ChunkingConfig:
    """
    Configuration for semantic chunking.
    """
    max_chars: int = 2200
    max_lines: int = 120
    overlap_lines: int = 4
    include_imports: bool = True
    include_module_code: bool = True
    min_meaningful_lines: int = 2


class CodeChunker:
    """
    Semantic code chunker that uses parsed structure when available.
    """

    def __init__(self) -> None:
        self.parser = CodeParser()

    def chunk_file(
        self,
        source: str,
        language: str,
        file_path: str,
        file_id: str = "",
        parse_result: Optional[dict[str, Any]] = None,
        config: Optional[ChunkingConfig] = None,
    ) -> list[dict[str, Any]]:
        """
        Chunk a source file into semantically meaningful chunks.

        Args:
            source: Full file content
            language: Programming language
            file_path: Relative file path
            file_id: DB file ID string
            parse_result: Optional parser output from Step 9
            config: Optional chunking config

        Returns:
            List of chunk dictionaries
        """
        cfg = config or ChunkingConfig()

        if not source or not source.strip():
            return []

        lines = source.splitlines()
        parsed = parse_result or self.parser.parse(source, language, file_path)
        functions = sorted(parsed.get("functions", []), key=lambda x: x.get("line_start", 0))
        classes = sorted(parsed.get("classes", []), key=lambda x: x.get("line_start", 0))
        imports = sorted(parsed.get("imports", []), key=lambda x: x.get("line", 0))

        chunks: list[dict[str, Any]] = []
        occupied: list[tuple[int, int]] = []

        # 1. Imports chunk
        if cfg.include_imports and imports:
            import_lines = [int(i["line"]) for i in imports if i.get("line")]
            if import_lines:
                start = min(import_lines)
                end = max(import_lines)
                chunk = self._build_chunk(
                    lines=lines,
                    file_id=file_id,
                    file_path=file_path,
                    language=language,
                    chunk_type="imports",
                    name="imports",
                    line_start=start,
                    line_end=end,
                    metadata={"imports": imports},
                )
                if chunk:
                    chunks.append(chunk)
                    occupied.append((start, end))

        class_ranges = [(int(c["line_start"]), int(c["line_end"]), c) for c in classes]

        # 2. Class chunks
        for start, end, cls in class_ranges:
            class_chunks = self._chunk_class(
                lines=lines,
                language=language,
                file_path=file_path,
                file_id=file_id,
                cls=cls,
                functions=functions,
                config=cfg,
            )
            chunks.extend(class_chunks)
            occupied.append((start, end))

        # 3. Standalone top-level functions
        for fn in functions:
            if fn.get("is_method"):
                continue
            start = int(fn.get("line_start", 1))
            end = int(fn.get("line_end", start))
            if self._inside_any_interval(start, class_ranges):
                continue
            fn_chunks = self._chunk_region(
                lines=lines,
                file_id=file_id,
                file_path=file_path,
                language=language,
                chunk_type="function",
                name=fn.get("name", "<anonymous>"),
                line_start=start,
                line_end=end,
                metadata={
                    "params": fn.get("params", []),
                    "return_type": fn.get("return_type"),
                    "docstring": fn.get("docstring"),
                },
                config=cfg,
            )
            chunks.extend(fn_chunks)
            occupied.append((start, end))

        # 4. Module-level residual code
        if cfg.include_module_code:
            merged = self._merge_intervals(occupied)
            for gap_start, gap_end in self._find_gaps(len(lines), merged):
                gap_chunks = self._chunk_gap(
                    lines=lines,
                    file_id=file_id,
                    file_path=file_path,
                    language=language,
                    line_start=gap_start,
                    line_end=gap_end,
                    config=cfg,
                )
                chunks.extend(gap_chunks)

        # 5. Fallback if nothing chunked
        if not chunks:
            chunks.extend(
                self._chunk_windows(
                    lines=lines,
                    file_id=file_id,
                    file_path=file_path,
                    language=language,
                    chunk_type="module",
                    name="file",
                    line_start=1,
                    line_end=len(lines),
                    metadata={},
                    config=cfg,
                )
            )

        # Deduplicate + sort
        deduped: dict[str, dict[str, Any]] = {}
        for chunk in chunks:
            key = f"{chunk['chunk_type']}|{chunk['name']}|{chunk['line_start']}|{chunk['line_end']}"
            deduped[key] = chunk

        ordered = sorted(
            deduped.values(),
            key=lambda c: (c["line_start"], c["line_end"], c["chunk_type"]),
        )
        logger.debug(f"Chunked {file_path}: {len(ordered)} chunks")
        return ordered

    def _chunk_class(
        self,
        lines: list[str],
        language: str,
        file_path: str,
        file_id: str,
        cls: dict[str, Any],
        functions: list[dict[str, Any]],
        config: ChunkingConfig,
    ) -> list[dict[str, Any]]:
        """
        Chunk a class. Large classes are split into header + methods.
        """
        class_name = cls.get("name", "<class>")
        start = int(cls.get("line_start", 1))
        end = int(cls.get("line_end", start))
        base_classes = cls.get("base_classes", [])

        text = self._slice_lines(lines, start, end)
        line_count = end - start + 1

        if len(text) <= config.max_chars and line_count <= config.max_lines:
            chunk = self._build_chunk(
                lines=lines,
                file_id=file_id,
                file_path=file_path,
                language=language,
                chunk_type="class",
                name=class_name,
                line_start=start,
                line_end=end,
                metadata={
                    "base_classes": base_classes,
                    "methods": cls.get("methods", []),
                    "docstring": cls.get("docstring"),
                },
            )
            return [chunk] if chunk else []

        # Large class: split into header + method chunks
        related_methods = [
            fn for fn in functions
            if fn.get("class_name") == class_name and fn.get("is_method")
        ]
        related_methods = sorted(related_methods, key=lambda x: x.get("line_start", 0))

        chunks: list[dict[str, Any]] = []

        if related_methods:
            header_end = int(related_methods[0]["line_start"]) - 1
            if header_end >= start:
                header = self._build_chunk(
                    lines=lines,
                    file_id=file_id,
                    file_path=file_path,
                    language=language,
                    chunk_type="class_header",
                    name=class_name,
                    line_start=start,
                    line_end=header_end,
                    metadata={"base_classes": base_classes},
                )
                if header:
                    chunks.append(header)

            for method in related_methods:
                method_chunks = self._chunk_region(
                    lines=lines,
                    file_id=file_id,
                    file_path=file_path,
                    language=language,
                    chunk_type="method",
                    name=f"{class_name}.{method.get('name')}",
                    line_start=int(method["line_start"]),
                    line_end=int(method["line_end"]),
                    metadata={
                        "class_name": class_name,
                        "params": method.get("params", []),
                        "return_type": method.get("return_type"),
                    },
                    config=config,
                )
                chunks.extend(method_chunks)

            return chunks

        # Fallback: line-window split
        return self._chunk_windows(
            lines=lines,
            file_id=file_id,
            file_path=file_path,
            language=language,
            chunk_type="class",
            name=class_name,
            line_start=start,
            line_end=end,
            metadata={"base_classes": base_classes},
            config=config,
        )

    def _chunk_gap(
        self,
        lines: list[str],
        file_id: str,
        file_path: str,
        language: str,
        line_start: int,
        line_end: int,
        config: ChunkingConfig,
    ) -> list[dict[str, Any]]:
        """
        Chunk module-level code between known structures.
        """
        text = self._slice_lines(lines, line_start, line_end)
        if not self._is_meaningful_block(text, config.min_meaningful_lines):
            return []

        return self._chunk_windows(
            lines=lines,
            file_id=file_id,
            file_path=file_path,
            language=language,
            chunk_type="module",
            name="module",
            line_start=line_start,
            line_end=line_end,
            metadata={},
            config=config,
        )

    def _chunk_region(
        self,
        lines: list[str],
        file_id: str,
        file_path: str,
        language: str,
        chunk_type: str,
        name: str,
        line_start: int,
        line_end: int,
        metadata: dict[str, Any],
        config: ChunkingConfig,
    ) -> list[dict[str, Any]]:
        """
        Chunk a single semantic region.
        If too large, split into windows.
        """
        text = self._slice_lines(lines, line_start, line_end)
        if not self._is_meaningful_block(text, config.min_meaningful_lines):
            return []

        line_count = line_end - line_start + 1
        if len(text) <= config.max_chars and line_count <= config.max_lines:
            chunk = self._build_chunk(
                lines=lines,
                file_id=file_id,
                file_path=file_path,
                language=language,
                chunk_type=chunk_type,
                name=name,
                line_start=line_start,
                line_end=line_end,
                metadata=metadata,
            )
            return [chunk] if chunk else []

        return self._chunk_windows(
            lines=lines,
            file_id=file_id,
            file_path=file_path,
            language=language,
            chunk_type=chunk_type,
            name=name,
            line_start=line_start,
            line_end=line_end,
            metadata=metadata,
            config=config,
        )

    def _chunk_windows(
        self,
        lines: list[str],
        file_id: str,
        file_path: str,
        language: str,
        chunk_type: str,
        name: str,
        line_start: int,
        line_end: int,
        metadata: dict[str, Any],
        config: ChunkingConfig,
    ) -> list[dict[str, Any]]:
        """
        Split a large region into overlapping line windows.
        """
        chunks: list[dict[str, Any]] = []
        current = line_start

        while current <= line_end:
            end = min(line_end, current + config.max_lines - 1)
            chunk = self._build_chunk(
                lines=lines,
                file_id=file_id,
                file_path=file_path,
                language=language,
                chunk_type=f"{chunk_type}_part",
                name=name,
                line_start=current,
                line_end=end,
                metadata=metadata,
            )
            if chunk:
                chunks.append(chunk)

            if end == line_end:
                break

            current = max(current + 1, end - config.overlap_lines + 1)

        return chunks

    def _build_chunk(
        self,
        lines: list[str],
        file_id: str,
        file_path: str,
        language: str,
        chunk_type: str,
        name: str,
        line_start: int,
        line_end: int,
        metadata: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """
        Build a chunk dictionary from line range.
        """
        content = self._slice_lines(lines, line_start, line_end)
        if not content.strip():
            return None

        char_count = len(content)
        token_estimate = max(1, char_count // 4)
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", name or "chunk")[:60]

        return {
            "chunk_id": f"{file_id}:{chunk_type}:{line_start}-{line_end}:{safe_name}",
            "file_id": file_id,
            "file_path": file_path,
            "language": language,
            "chunk_type": chunk_type,
            "name": name,
            "line_start": line_start,
            "line_end": line_end,
            "char_count": char_count,
            "token_estimate": token_estimate,
            "content": content,
            "content_preview": content[:180],
            "metadata": metadata,
        }

    def _slice_lines(self, lines: list[str], start: int, end: int) -> str:
        """
        Slice 1-indexed inclusive line range from a list of lines.
        """
        if start < 1:
            start = 1
        if end > len(lines):
            end = len(lines)
        if end < start:
            return ""
        return "\n".join(lines[start - 1:end])

    def _merge_intervals(self, intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """
        Merge overlapping line intervals.
        """
        if not intervals:
            return []
        sorted_intervals = sorted(intervals, key=lambda x: x[0])
        merged = [sorted_intervals[0]]

        for start, end in sorted_intervals[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end + 1:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))

        return merged

    def _find_gaps(
        self,
        total_lines: int,
        occupied: list[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        """
        Find uncovered line gaps between occupied intervals.
        """
        if total_lines <= 0:
            return []

        if not occupied:
            return [(1, total_lines)]

        gaps: list[tuple[int, int]] = []
        current = 1

        for start, end in occupied:
            if current < start:
                gaps.append((current, start - 1))
            current = max(current, end + 1)

        if current <= total_lines:
            gaps.append((current, total_lines))

        return gaps

    def _inside_any_interval(
        self,
        line_no: int,
        class_ranges: list[tuple[int, int, dict[str, Any]]],
    ) -> bool:
        """
        Check whether a line falls inside any class interval.
        """
        for start, end, _ in class_ranges:
            if start <= line_no <= end:
                return True
        return False

    def _is_meaningful_block(self, text: str, min_lines: int) -> bool:
        """
        Determine whether a block contains meaningful code.
        Ignores blank lines and comment-only lines.
        """
        meaningful = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#") or stripped.startswith("//"):
                continue
            meaningful.append(stripped)

        return len(meaningful) >= min_lines