"""
Code Similarity Detection Engine - Step 38
AI Codebase Assistant v2.0

Finds duplicate and near-duplicate code across a codebase using
three complementary algorithms:

1. Exact Duplicate Detection (MD5 hashing):
   - Normalize → hash → group identical blocks
   - O(n) per file — extremely fast
   - Zero false positives
   - Finds copy-pasted code blocks

2. Token Jaccard Similarity:
   - Tokenize code → set of token n-grams
   - Jaccard(A,B) = |A∩B| / |A∪B|
   - O(n²) pairs but runs on small candidate sets
   - Threshold: 0.7 = 70% token overlap
   - Finds near-duplicates with minor edits

3. MinHash LSH (Locality Sensitive Hashing):
   - Approximates Jaccard similarity in O(n) time
   - Uses 128 hash functions for fingerprint
   - Groups similar documents via LSH bands
   - Scalable to thousands of files
   - Best for large codebase scans

Output per similarity pair:
    {
        "file_a": str,
        "file_b": str,
        "similarity_score": float,    # 0.0 to 1.0
        "algorithm": str,             # exact | jaccard | minhash
        "snippet_a": str,             # code snippet from file A
        "snippet_b": str,             # code snippet from file B
        "lines_a": [int, int],        # [start, end] in file A
        "lines_b": [int, int],        # [start, end] in file B
        "savings_lines": int,         # lines that could be eliminated
    }

Project report:
    {
        "total_pairs": int,
        "exact_duplicates": int,
        "near_duplicates": int,
        "duplicate_ratio": float,     # % of codebase that is duplicate
        "estimated_savings_lines": int,
        "pairs": list[dict],          # top 50 similarity pairs
        "most_duplicated_files": list # files with most duplicates
    }
"""

from __future__ import annotations

import hashlib
import re
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# =============================================================================
# Code Normalizer
# =============================================================================

class CodeNormalizer:
    """
    Normalizes source code for comparison by removing noise.

    Normalization steps:
        1. Strip comments (single-line and multi-line)
        2. Normalize whitespace (collapse spaces, strip blank lines)
        3. Lowercase (for case-insensitive comparison)
        4. Remove string literals (replace with placeholder)

    This allows finding near-duplicates even when variable names,
    comments, or string values differ.
    """

    # Patterns for stripping
    PYTHON_COMMENT = re.compile(r'#[^\n]*')
    PYTHON_DOCSTRING = re.compile(r'""".*?"""|\'\'\'.*?\'\'\'', re.DOTALL)
    JS_LINE_COMMENT = re.compile(r'//[^\n]*')
    JS_BLOCK_COMMENT = re.compile(r'/\*.*?\*/', re.DOTALL)
    STRING_LITERAL = re.compile(
        r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`(?:[^`\\]|\\.)*`'
    )
    WHITESPACE = re.compile(r'\s+')
    BLANK_LINE = re.compile(r'\n\s*\n')

    @classmethod
    def normalize(
        cls,
        source: str,
        language: str = "unknown",
        aggressive: bool = False,
    ) -> str:
        """
        Normalize source code for similarity comparison.

        Args:
            source:     Raw source code string
            language:   Programming language (affects comment stripping)
            aggressive: If True, also remove identifiers and literals

        Returns:
            Normalized code string
        """
        # Strip docstrings and comments first
        if language == "python":
            source = cls.PYTHON_DOCSTRING.sub(" ", source)
            source = cls.PYTHON_COMMENT.sub("", source)
        elif language in ("javascript", "typescript", "js", "ts",
                          "jsx", "tsx"):
            source = cls.JS_BLOCK_COMMENT.sub(" ", source)
            source = cls.JS_LINE_COMMENT.sub("", source)
        else:
            # Generic: try both styles
            source = cls.JS_BLOCK_COMMENT.sub(" ", source)
            source = cls.JS_LINE_COMMENT.sub("", source)
            source = cls.PYTHON_COMMENT.sub("", source)

        if aggressive:
            # Replace string literals with placeholder
            source = cls.STRING_LITERAL.sub('"STR"', source)

        # Normalize whitespace
        source = cls.WHITESPACE.sub(" ", source)
        source = source.strip()

        return source

    @classmethod
    def normalize_line(cls, line: str) -> str:
        """
        Normalize a single line for comparison.

        Args:
            line: Source code line

        Returns:
            Normalized line (stripped, lowercased)
        """
        # Remove inline comments
        line = cls.PYTHON_COMMENT.sub("", line)
        line = cls.JS_LINE_COMMENT.sub("", line)
        return line.strip().lower()


# =============================================================================
# Tokenizer
# =============================================================================

class CodeTokenizer:
    """
    Tokenizes source code into a set of tokens for similarity computation.

    Uses a simple regex tokenizer that captures:
        - Identifiers (variable names, function names)
        - Keywords
        - Operators
        - Numeric literals (normalized to "NUM")

    Returns n-gram shingles for better locality sensitivity.
    """

    TOKEN_PAT = re.compile(
        r'\b[a-zA-Z_]\w*\b'    # identifiers
        r'|\b\d+\.?\d*\b'       # numbers
        r'|[+\-*/=<>!&|^~?:;,(){}[\].]'  # operators/punctuation
    )

    # Tokens to filter out (too common to be useful)
    STOP_TOKENS: frozenset[str] = frozenset([
        "the", "a", "an",  # English words that might appear in names
        "if", "else", "for", "while", "return", "def", "class",
        "function", "var", "let", "const", "import", "export",
        "public", "private", "static", "void", "int", "string",
        "self", "this", "true", "false", "null", "none",
        "0", "1", "2", "-1",
    ])

    @classmethod
    def tokenize(cls, source: str, shingle_size: int = 3) -> set[str]:
        """
        Tokenize source code into a set of n-gram shingles.

        Args:
            source:       Source code string (should be normalized first)
            shingle_size: Size of n-gram window (3 = trigrams)

        Returns:
            Set of token n-gram strings
        """
        tokens = cls.TOKEN_PAT.findall(source.lower())
        # Filter stop tokens and very short tokens
        tokens = [t for t in tokens if t not in cls.STOP_TOKENS
                  and len(t) > 1]

        if len(tokens) < shingle_size:
            return set(tokens)

        # Create shingles (n-grams)
        shingles: set[str] = set()
        for i in range(len(tokens) - shingle_size + 1):
            shingle = " ".join(tokens[i:i + shingle_size])
            shingles.add(shingle)

        return shingles

    @classmethod
    def tokenize_lines(cls, source: str) -> list[str]:
        """
        Tokenize each line for line-level similarity.

        Args:
            source: Multi-line source code

        Returns:
            List of normalized line strings
        """
        return [
            CodeNormalizer.normalize_line(line)
            for line in source.splitlines()
            if line.strip()
        ]


# =============================================================================
# MinHash Implementation
# =============================================================================

class MinHasher:
    """
    MinHash signature generator for approximate Jaccard similarity.

    Uses 128 independent hash functions to create a compact
    signature (fingerprint) for each document. Documents with
    similar MinHash signatures have high Jaccard similarity.

    Hash function: h_i(x) = (a_i * x + b_i) mod p
    where p is a large prime and a_i, b_i are random coefficients.
    """

    # Large prime for hash function
    _PRIME = (1 << 61) - 1

    def __init__(self, num_hashes: int = 128) -> None:
        """
        Initialize MinHasher with hash function parameters.

        Args:
            num_hashes: Number of hash functions (more = more accurate,
                        but slower). 128 gives ~1% error for Jaccard.
        """
        self.num_hashes = num_hashes
        # Generate random coefficients for hash functions
        # Using deterministic seed for reproducibility
        import random
        rng = random.Random(42)
        self._a = [rng.randint(1, self._PRIME - 1) for _ in range(num_hashes)]
        self._b = [rng.randint(0, self._PRIME - 1) for _ in range(num_hashes)]

    def signature(self, shingles: set[str]) -> list[int]:
        """
        Compute MinHash signature for a set of shingles.

        Args:
            shingles: Set of shingle strings from CodeTokenizer

        Returns:
            List of num_hashes integers (the MinHash signature)
        """
        if not shingles:
            return [0] * self.num_hashes

        sig = [float("inf")] * self.num_hashes

        for shingle in shingles:
            # Hash the shingle string to an integer
            h = int(hashlib.md5(shingle.encode()).hexdigest(), 16)

            # Apply each hash function
            for i in range(self.num_hashes):
                val = (self._a[i] * h + self._b[i]) % self._PRIME
                if val < sig[i]:
                    sig[i] = val

        return [int(x) for x in sig]

    def estimate_jaccard(
        self,
        sig_a: list[int],
        sig_b: list[int],
    ) -> float:
        """
        Estimate Jaccard similarity from two MinHash signatures.

        Args:
            sig_a: MinHash signature of document A
            sig_b: MinHash signature of document B

        Returns:
            Estimated Jaccard similarity in [0.0, 1.0]
        """
        if not sig_a or not sig_b:
            return 0.0
        matches = sum(a == b for a, b in zip(sig_a, sig_b))
        return matches / self.num_hashes


# =============================================================================
# LSH Banding
# =============================================================================

class LSHIndex:
    """
    Locality Sensitive Hashing index for fast approximate similarity search.

    Groups documents into bands of hash buckets. Documents that share
    a bucket in ANY band are candidate pairs for detailed comparison.

    Configuration:
        bands=32, rows=4 (128 hashes total)
        → Probability of being candidate at Jaccard=0.5 is ~86%
        → False positive rate is low with subsequent Jaccard verification
    """

    def __init__(
        self,
        bands: int = 32,
        rows: int = 4,
    ) -> None:
        """
        Initialize LSH index.

        Args:
            bands: Number of bands (more bands = higher recall)
            rows:  Hash functions per band (more rows = higher precision)
        """
        self.bands = bands
        self.rows = rows
        self.num_hashes = bands * rows
        # bucket[band_idx][bucket_hash] = [doc_id, ...]
        self._buckets: list[dict[int, list[str]]] = [
            {} for _ in range(bands)
        ]

    def add(self, doc_id: str, signature: list[int]) -> None:
        """
        Add a document's MinHash signature to the LSH index.

        Args:
            doc_id:    Unique document identifier (file path)
            signature: MinHash signature list
        """
        for band_idx in range(self.bands):
            start = band_idx * self.rows
            end = start + self.rows
            band_sig = tuple(signature[start:end])

            # Hash the band signature to a bucket
            bucket_hash = hash(band_sig)

            if bucket_hash not in self._buckets[band_idx]:
                self._buckets[band_idx][bucket_hash] = []
            self._buckets[band_idx][bucket_hash].append(doc_id)

    def get_candidates(self) -> set[tuple[str, str]]:
        """
        Get all candidate similar pairs from the LSH index.

        Returns all pairs that share at least one bucket in any band.

        Returns:
            Set of (doc_id_a, doc_id_b) tuples (sorted so a < b)
        """
        candidates: set[tuple[str, str]] = set()

        for band_idx in range(self.bands):
            for bucket_hash, doc_ids in self._buckets[band_idx].items():
                if len(doc_ids) < 2:
                    continue
                # Add all pairs in this bucket
                for i in range(len(doc_ids)):
                    for j in range(i + 1, len(doc_ids)):
                        pair = tuple(sorted([doc_ids[i], doc_ids[j]]))
                        candidates.add(pair)

        return candidates


# =============================================================================
# Exact Duplicate Detector
# =============================================================================

class ExactDuplicateDetector:
    """
    Detects exact code duplicates using MD5 hashing.

    Operates on normalized code blocks (comments stripped,
    whitespace normalized) for robustness to formatting changes.
    """

    @staticmethod
    def find_exact_duplicates(
        files: list[dict[str, str]],
        min_lines: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Find files with identical normalized content.

        Args:
            files:     List of {"path": str, "content": str} dicts
            min_lines: Minimum lines for a file to be checked

        Returns:
            List of exact duplicate pair dicts
        """
        hash_to_files: dict[str, list[dict[str, str]]] = defaultdict(list)

        for f in files:
            path = str(f.get("path") or "")
            content = str(f.get("content") or "")

            lines = [l for l in content.splitlines() if l.strip()]
            if len(lines) < min_lines:
                continue

            # Normalize and hash
            normalized = CodeNormalizer.normalize(content)
            content_hash = hashlib.md5(normalized.encode()).hexdigest()
            hash_to_files[content_hash].append({
                "path": path,
                "content": content,
                "lines": len(lines),
            })

        pairs: list[dict[str, Any]] = []
        for content_hash, file_list in hash_to_files.items():
            if len(file_list) < 2:
                continue
            # Create pairs from all files with same hash
            for i in range(len(file_list)):
                for j in range(i + 1, len(file_list)):
                    fa = file_list[i]
                    fb = file_list[j]
                    lines_a = fa["content"].splitlines()
                    lines_b = fb["content"].splitlines()
                    pairs.append({
                        "file_a": fa["path"],
                        "file_b": fb["path"],
                        "similarity_score": 1.0,
                        "algorithm": "exact",
                        "snippet_a": "\n".join(lines_a[:10]),
                        "snippet_b": "\n".join(lines_b[:10]),
                        "lines_a": [1, fa["lines"]],
                        "lines_b": [1, fb["lines"]],
                        "savings_lines": min(fa["lines"], fb["lines"]),
                    })

        return pairs


# =============================================================================
# Jaccard Similarity Calculator
# =============================================================================

class JaccardSimilarityDetector:
    """
    Finds near-duplicate code using token-based Jaccard similarity.

    Best for smaller codebases (< 500 files) where O(n²) is acceptable.
    Produces exact Jaccard scores unlike MinHash approximation.
    """

    @staticmethod
    def jaccard(set_a: set[str], set_b: set[str]) -> float:
        """
        Calculate exact Jaccard similarity between two token sets.

        Args:
            set_a: Token shingle set for document A
            set_b: Token shingle set for document B

        Returns:
            Jaccard similarity in [0.0, 1.0]
        """
        if not set_a and not set_b:
            return 1.0
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    @classmethod
    def find_similar_pairs(
        cls,
        files: list[dict[str, str]],
        threshold: float = 0.7,
        min_lines: int = 10,
        max_files: int = 200,
    ) -> list[dict[str, Any]]:
        """
        Find near-duplicate file pairs using Jaccard similarity.

        Args:
            files:     File list
            threshold: Minimum Jaccard score to report (0.0-1.0)
            min_lines: Minimum file lines to include
            max_files: Max files to process (O(n²) scalability limit)

        Returns:
            List of similar pair dicts sorted by score descending
        """
        # Build shingle sets
        file_shingles: list[tuple[str, set[str], str, int]] = []
        for f in files[:max_files]:
            path = str(f.get("path") or "")
            content = str(f.get("content") or "")
            lines = [l for l in content.splitlines() if l.strip()]
            if len(lines) < min_lines:
                continue
            normalized = CodeNormalizer.normalize(content)
            shingles = CodeTokenizer.tokenize(normalized)
            if shingles:
                file_shingles.append((path, shingles, content, len(lines)))

        pairs: list[dict[str, Any]] = []

        # O(n²) comparison
        for i in range(len(file_shingles)):
            for j in range(i + 1, len(file_shingles)):
                path_a, shingles_a, content_a, lines_a = file_shingles[i]
                path_b, shingles_b, content_b, lines_b = file_shingles[j]

                score = cls.jaccard(shingles_a, shingles_b)
                if score >= threshold:
                    snippet_a = "\n".join(content_a.splitlines()[:10])
                    snippet_b = "\n".join(content_b.splitlines()[:10])
                    pairs.append({
                        "file_a": path_a,
                        "file_b": path_b,
                        "similarity_score": round(score, 4),
                        "algorithm": "jaccard",
                        "snippet_a": snippet_a,
                        "snippet_b": snippet_b,
                        "lines_a": [1, lines_a],
                        "lines_b": [1, lines_b],
                        "savings_lines": min(lines_a, lines_b),
                    })

        pairs.sort(key=lambda x: x["similarity_score"], reverse=True)
        return pairs


# =============================================================================
# MinHash LSH Detector
# =============================================================================

class MinHashLSHDetector:
    """
    Scalable near-duplicate detection using MinHash + LSH.

    Scales to thousands of files in near-linear time.
    Trade-off: approximate similarity scores (within ~2% of true Jaccard).
    """

    def __init__(
        self,
        num_hashes: int = 128,
        bands: int = 32,
        threshold: float = 0.6,
    ) -> None:
        """
        Initialize MinHash LSH detector.

        Args:
            num_hashes: Hash functions for MinHash (128 = ~1% error)
            bands:      LSH bands (32 bands × 4 rows = 128 hashes)
            threshold:  Minimum similarity to report
        """
        self.threshold = threshold
        self._hasher = MinHasher(num_hashes)
        self._lsh = LSHIndex(bands=bands, rows=num_hashes // bands)

    def find_similar_pairs(
        self,
        files: list[dict[str, str]],
        min_lines: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Find near-duplicate file pairs using MinHash LSH.

        Phase 1: Compute MinHash signatures for all files — O(n)
        Phase 2: Index into LSH bands — O(n)
        Phase 3: Get candidate pairs from LSH — O(candidates)
        Phase 4: Verify candidates with exact Jaccard — O(candidates²)

        Args:
            files:     File list
            min_lines: Minimum file size to include

        Returns:
            List of similar pair dicts
        """
        # Phase 1 + 2: Compute signatures and build index
        file_data: dict[str, dict[str, Any]] = {}

        for f in files:
            path = str(f.get("path") or "")
            content = str(f.get("content") or "")
            lines = [l for l in content.splitlines() if l.strip()]
            if len(lines) < min_lines:
                continue

            normalized = CodeNormalizer.normalize(content)
            shingles = CodeTokenizer.tokenize(normalized)
            if not shingles:
                continue

            sig = self._hasher.signature(shingles)
            self._lsh.add(path, sig)

            file_data[path] = {
                "path": path,
                "content": content,
                "shingles": shingles,
                "signature": sig,
                "lines": len(lines),
            }

        # Phase 3: Get candidate pairs
        candidates = self._lsh.get_candidates()

        # Phase 4: Verify candidates
        pairs: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for path_a, path_b in candidates:
            if path_a not in file_data or path_b not in file_data:
                continue
            pair_key = (min(path_a, path_b), max(path_a, path_b))
            if pair_key in seen:
                continue
            seen.add(pair_key)

            da = file_data[path_a]
            db = file_data[path_b]

            # Use exact Jaccard for final verification
            score = JaccardSimilarityDetector.jaccard(
                da["shingles"], db["shingles"]
            )

            if score >= self.threshold:
                snippet_a = "\n".join(da["content"].splitlines()[:10])
                snippet_b = "\n".join(db["content"].splitlines()[:10])
                pairs.append({
                    "file_a": path_a,
                    "file_b": path_b,
                    "similarity_score": round(score, 4),
                    "algorithm": "minhash_lsh",
                    "snippet_a": snippet_a,
                    "snippet_b": snippet_b,
                    "lines_a": [1, da["lines"]],
                    "lines_b": [1, db["lines"]],
                    "savings_lines": min(da["lines"], db["lines"]),
                })

        pairs.sort(key=lambda x: x["similarity_score"], reverse=True)
        return pairs


# =============================================================================
# Line-Level Similarity (within a file)
# =============================================================================

class IntraFileSimilarityDetector:
    """
    Detects duplicate code blocks WITHIN a single file.

    Uses a sliding window of normalized lines and hashing to find
    repeated code patterns inside one file. Especially useful for
    finding copy-pasted function bodies.
    """

    @staticmethod
    def find_duplicate_blocks(
        content: str,
        window_lines: int = 8,
        min_similarity: float = 0.85,
    ) -> list[dict[str, Any]]:
        """
        Find duplicate code blocks within a single file.

        Args:
            content:        File content string
            window_lines:   Lines per sliding window block
            min_similarity: Minimum similarity to report (0.0-1.0)

        Returns:
            List of intra-file duplicate block dicts
        """
        lines = [l for l in content.splitlines() if l.strip()]
        if len(lines) < window_lines * 2:
            return []

        # Normalize each line
        norm_lines = [CodeNormalizer.normalize_line(l) for l in lines]

        # Hash each window
        window_hashes: dict[str, list[int]] = defaultdict(list)
        for i in range(len(norm_lines) - window_lines + 1):
            window = "\n".join(norm_lines[i:i + window_lines])
            window_hash = hashlib.md5(window.encode()).hexdigest()
            window_hashes[window_hash].append(i)

        # Find duplicate windows
        duplicates: list[dict[str, Any]] = []
        for window_hash, positions in window_hashes.items():
            if len(positions) < 2:
                continue
            # Report first two occurrences
            pos_a = positions[0]
            pos_b = positions[1]
            if pos_b - pos_a < window_lines:
                continue  # Overlapping windows

            snippet_a = "\n".join(lines[pos_a:pos_a + window_lines])
            snippet_b = "\n".join(lines[pos_b:pos_b + window_lines])
            duplicates.append({
                "file_a": "same_file",
                "file_b": "same_file",
                "similarity_score": 1.0,
                "algorithm": "intra_file_exact",
                "snippet_a": snippet_a,
                "snippet_b": snippet_b,
                "lines_a": [pos_a + 1, pos_a + window_lines],
                "lines_b": [pos_b + 1, pos_b + window_lines],
                "savings_lines": window_lines,
                "occurrences": len(positions),
            })

        return duplicates[:10]  # Cap at 10 per file


# =============================================================================
# Main Similarity Engine
# =============================================================================

class SimilarityEngine:
    """
    Main entry point for code similarity analysis.

    Orchestrates exact, Jaccard, and MinHash LSH detection
    and aggregates results into a unified project report.
    """

    def __init__(self) -> None:
        """Initialize with sub-detectors."""
        self._minhash_detector = MinHashLSHDetector(
            num_hashes=128,
            bands=32,
            threshold=0.6,
        )

    def analyze_project(
        self,
        files: list[dict[str, str]],
        threshold: float = 0.7,
        algorithm: str = "auto",
    ) -> dict[str, Any]:
        """
        Analyze a project for code similarity and duplicates.

        Algorithm selection:
            auto   - Use Jaccard for < 100 files, MinHash for >= 100
            exact  - Only exact duplicate detection
            jaccard - Only Jaccard similarity
            minhash - Only MinHash LSH

        Args:
            files:     List of {"path": str, "content": str} dicts
            threshold: Similarity threshold (0.0-1.0)
            algorithm: Which algorithm to use

        Returns:
            Project similarity report dict
        """
        if not files:
            return self._empty_report()

        # Step 1: Always run exact duplicate detection (O(n), very fast)
        exact_pairs = ExactDuplicateDetector.find_exact_duplicates(
            files, min_lines=5
        )

        # Step 2: Run similarity detection based on algorithm choice
        near_pairs: list[dict[str, Any]] = []

        if algorithm == "exact":
            pass  # Only exact
        elif algorithm == "jaccard" or (
            algorithm == "auto" and len(files) < 100
        ):
            near_pairs = JaccardSimilarityDetector.find_similar_pairs(
                files,
                threshold=threshold,
                min_lines=10,
            )
            # Remove exact duplicates from near-pairs (avoid double-reporting)
            exact_file_pairs = {
                (p["file_a"], p["file_b"]) for p in exact_pairs
            }
            near_pairs = [
                p for p in near_pairs
                if (p["file_a"], p["file_b"]) not in exact_file_pairs
                and p["similarity_score"] < 1.0
            ]
        else:
            # MinHash LSH for large codebases
            self._minhash_detector.threshold = threshold
            near_pairs = self._minhash_detector.find_similar_pairs(
                files, min_lines=10
            )
            exact_file_pairs = {
                (p["file_a"], p["file_b"]) for p in exact_pairs
            }
            near_pairs = [
                p for p in near_pairs
                if (p["file_a"], p["file_b"]) not in exact_file_pairs
                and p["similarity_score"] < 1.0
            ]

        # Combine all pairs
        all_pairs = exact_pairs + near_pairs
        all_pairs.sort(key=lambda x: x["similarity_score"], reverse=True)

        # Step 3: Calculate metrics
        total_lines = sum(
            len([l for l in str(f.get("content", "")).splitlines()
                 if l.strip()])
            for f in files
        )
        savings = sum(p.get("savings_lines", 0) for p in all_pairs)

        # Files involved in duplicates
        dup_files: Counter = Counter()
        for pair in all_pairs:
            dup_files[pair["file_a"]] += 1
            dup_files[pair["file_b"]] += 1

        most_duplicated = [
            {"file": path, "duplicate_count": count}
            for path, count in dup_files.most_common(10)
        ]

        return {
            "total_files_analyzed": len(files),
            "total_pairs": len(all_pairs),
            "exact_duplicates": len(exact_pairs),
            "near_duplicates": len(near_pairs),
            "duplicate_ratio": round(
                len(set(
                    p for pair in all_pairs
                    for p in [pair["file_a"], pair["file_b"]]
                )) / max(len(files), 1) * 100, 1
            ),
            "estimated_savings_lines": savings,
            "total_lines_analyzed": total_lines,
            "algorithm_used": algorithm,
            "pairs": all_pairs[:50],  # Return top 50
            "most_duplicated_files": most_duplicated,
        }

    def analyze_file(
        self,
        content: str,
        file_path: str = "unknown",
        window_lines: int = 8,
    ) -> dict[str, Any]:
        """
        Find duplicate blocks within a single file.

        Args:
            content:      File content string
            file_path:    File path for context
            window_lines: Lines per comparison window

        Returns:
            Intra-file duplicate report
        """
        duplicates = IntraFileSimilarityDetector.find_duplicate_blocks(
            content, window_lines=window_lines
        )
        return {
            "file_path": file_path,
            "duplicate_blocks": len(duplicates),
            "blocks": duplicates,
            "estimated_savings_lines": sum(
                d.get("savings_lines", 0) for d in duplicates
            ),
        }

    def compare_two_files(
        self,
        content_a: str,
        path_a: str,
        content_b: str,
        path_b: str,
    ) -> dict[str, Any]:
        """
        Compute similarity between exactly two files.

        Args:
            content_a: Content of file A
            path_a:    Path of file A
            content_b: Content of file B
            path_b:    Path of file B

        Returns:
            Similarity result dict with score and algorithm details
        """
        norm_a = CodeNormalizer.normalize(content_a)
        norm_b = CodeNormalizer.normalize(content_b)

        shingles_a = CodeTokenizer.tokenize(norm_a)
        shingles_b = CodeTokenizer.tokenize(norm_b)

        jaccard_score = JaccardSimilarityDetector.jaccard(
            shingles_a, shingles_b
        )

        # Also check exact match
        hash_a = hashlib.md5(norm_a.encode()).hexdigest()
        hash_b = hashlib.md5(norm_b.encode()).hexdigest()
        is_exact = hash_a == hash_b

        lines_a = [l for l in content_a.splitlines() if l.strip()]
        lines_b = [l for l in content_b.splitlines() if l.strip()]

        return {
            "file_a": path_a,
            "file_b": path_b,
            "similarity_score": 1.0 if is_exact else round(jaccard_score, 4),
            "is_exact_duplicate": is_exact,
            "jaccard_score": round(jaccard_score, 4),
            "lines_a": len(lines_a),
            "lines_b": len(lines_b),
            "tokens_a": len(shingles_a),
            "tokens_b": len(shingles_b),
            "shared_tokens": len(shingles_a & shingles_b),
            "snippet_a": "\n".join(lines_a[:8]),
            "snippet_b": "\n".join(lines_b[:8]),
        }

    @staticmethod
    def _empty_report() -> dict[str, Any]:
        """Return an empty similarity report."""
        return {
            "total_files_analyzed": 0,
            "total_pairs": 0,
            "exact_duplicates": 0,
            "near_duplicates": 0,
            "duplicate_ratio": 0.0,
            "estimated_savings_lines": 0,
            "total_lines_analyzed": 0,
            "algorithm_used": "none",
            "pairs": [],
            "most_duplicated_files": [],
        }
