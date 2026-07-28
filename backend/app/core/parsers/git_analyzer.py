"""
Git History Analyzer - Step 34
AI Codebase Assistant v2.0

Analyzes git log data to extract:
    Hotspots:       Files changed most frequently
    Churn:          Files with most lines added/removed
    Contributors:   Per-author commit/file stats
    Bug commits:    Commits with fix/bug/error keywords
    Co-changes:     Files that change together (coupling)
    Velocity:       Commit frequency over time (weekly buckets)
    Blame summary:  Line ownership per file (from git blame output)

Input format (accepts pre-parsed git log):
    Git log format string used to extract:
        --pretty=format:"%H|%ae|%an|%ad|%s" --date=iso --numstat

    This format produces entries like:
        abc123|dev@co.com|Alice|2024-01-15 10:30:00 +0000|Fix login bug
        5\t2\tsrc/auth/login.py
        10\t3\tsrc/utils/helpers.py

    Pass as a list of GitCommit dicts to avoid needing git on the server.

Output:
    hotspots, contributor_stats, churn_analysis, co_change_pairs,
    velocity_data, bug_commit_files, summary
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class GitCommit:
    """
    Represents a single git commit with its file changes.

    Attributes:
        hash:         Full commit SHA
        author_email: Author email address
        author_name:  Author display name
        date:         Commit timestamp (ISO format string or datetime)
        message:      Commit message subject line
        files_changed: List of FileChange dicts
    """
    hash: str
    author_email: str
    author_name: str
    date: str
    message: str
    files_changed: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FileChange:
    """
    Represents a single file's change stats within a commit.

    Attributes:
        path:      File path
        additions: Lines added
        deletions: Lines deleted
        is_rename: True if file was renamed in this commit
        old_path:  Previous path if renamed
    """
    path: str
    additions: int = 0
    deletions: int = 0
    is_rename: bool = False
    old_path: str = ""


# =============================================================================
# Git Log Parser
# =============================================================================

class GitLogParser:
    """
    Parses raw git log output into structured GitCommit objects.

    Expects git log generated with:
        git log --pretty=format:"%H|%ae|%an|%ad|%s" --date=iso --numstat

    Output alternates between:
        commit line: "hash|email|name|date|message"
        numstat lines: "additions\tdeletions\tpath"
        blank line (separator)
    """

    # Regex for the commit header line
    COMMIT_PAT = re.compile(
        r'^([0-9a-f]{4,40})\|([^|]+)\|([^|]+)\|([^|]+)\|(.*)$'
    )
    # Regex for numstat file lines
    NUMSTAT_PAT = re.compile(r'^(\d+|-)\t(\d+|-)\t(.+)$')
    # Rename pattern: {old => new}/path
    RENAME_PAT = re.compile(r'\{([^}]+)\s+=>\s+([^}]*)\}')

    @classmethod
    def parse(cls, raw_log: str) -> list[GitCommit]:
        """
        Parse raw git log string into a list of GitCommit objects.

        Args:
            raw_log: Raw output from git log --numstat command

        Returns:
            List of GitCommit objects ordered newest-first
        """
        commits: list[GitCommit] = []
        current_commit: GitCommit | None = None

        for line in raw_log.splitlines():
            line = line.rstrip()

            # Blank line — separator between commits
            if not line:
                continue

            # Try commit header
            commit_match = cls.COMMIT_PAT.match(line)
            if commit_match:
                if current_commit:
                    commits.append(current_commit)
                current_commit = GitCommit(
                    hash=commit_match.group(1),
                    author_email=commit_match.group(2).strip(),
                    author_name=commit_match.group(3).strip(),
                    date=commit_match.group(4).strip(),
                    message=commit_match.group(5).strip(),
                    files_changed=[],
                )
                continue

            # Try numstat file line
            numstat_match = cls.NUMSTAT_PAT.match(line)
            if numstat_match and current_commit:
                additions_str = numstat_match.group(1)
                deletions_str = numstat_match.group(2)
                path = numstat_match.group(3).strip()

                # Binary files show as "-"
                additions = (
                    int(additions_str)
                    if additions_str != "-" else 0
                )
                deletions = (
                    int(deletions_str)
                    if deletions_str != "-" else 0
                )

                # Handle renames: {old => new} syntax
                is_rename = False
                old_path = ""
                rename_match = cls.RENAME_PAT.search(path)
                if rename_match:
                    is_rename = True
                    old_part = rename_match.group(1)
                    new_part = rename_match.group(2)
                    prefix = path[:rename_match.start()]
                    suffix = path[rename_match.end():]
                    old_path = prefix + old_part + suffix
                    path = prefix + new_part + suffix

                current_commit.files_changed.append({
                    "path": path,
                    "additions": additions,
                    "deletions": deletions,
                    "is_rename": is_rename,
                    "old_path": old_path,
                })

        # Don't forget the last commit
        if current_commit:
            commits.append(current_commit)

        return commits

    @classmethod
    def parse_from_dicts(cls, commit_dicts: list[dict[str, Any]]) -> list[GitCommit]:
        """
        Parse commit history from a list of dicts (API input format).

        Args:
            commit_dicts: List of commit dicts with keys matching GitCommit fields

        Returns:
            List of GitCommit objects
        """
        commits: list[GitCommit] = []
        for d in commit_dicts:
            commit = GitCommit(
                hash=str(d.get("hash") or d.get("sha") or ""),
                author_email=str(d.get("author_email") or d.get("email") or ""),
                author_name=str(d.get("author_name") or d.get("author") or ""),
                date=str(d.get("date") or d.get("timestamp") or ""),
                message=str(d.get("message") or d.get("subject") or ""),
                files_changed=[
                    fc if isinstance(fc, dict) else {"path": str(fc), "additions": 0, "deletions": 0}
                    for fc in (d.get("files_changed") or d.get("files") or [])
                ],
            )
            commits.append(commit)
        return commits


# =============================================================================
# Hotspot Analyzer
# =============================================================================

class HotspotAnalyzer:
    """
    Identifies files most frequently changed in git history.

    Hotspot files are high-churn files — they change often and are
    likely to contain bugs, be overly coupled, or need refactoring.
    Combines with complexity metrics for a risk matrix.
    """

    # Keywords indicating bug-fix commits
    BUG_KEYWORDS = frozenset([
        "fix", "bug", "error", "crash", "issue", "defect",
        "broken", "revert", "hotfix", "patch", "repair",
        "regression", "fail", "failure", "incorrect", "wrong",
    ])

    @classmethod
    def analyze(cls, commits: list[GitCommit]) -> dict[str, Any]:
        """
        Analyze commit history and return hotspot data.

        Args:
            commits: List of GitCommit objects

        Returns:
            Dict with hotspots, bug_files, contributor_stats,
            churn_by_file, co_changes, velocity
        """
        # ── File change frequency ──────────────────────────────────
        file_commit_count: Counter = Counter()
        file_additions: Counter = Counter()
        file_deletions: Counter = Counter()
        file_authors: dict[str, set[str]] = defaultdict(set)
        file_bug_commits: Counter = Counter()

        # ── Author stats ───────────────────────────────────────────
        author_commits: Counter = Counter()
        author_files: dict[str, set[str]] = defaultdict(set)
        author_additions: Counter = Counter()
        author_deletions: Counter = Counter()
        author_bug_commits: Counter = Counter()

        # ── Co-change pairs ───────────────────────────────────────
        co_change_pairs: Counter = Counter()

        # ── Weekly velocity ───────────────────────────────────────
        weekly_commits: Counter = Counter()

        # ── Process each commit ───────────────────────────────────
        is_bug_commit_cache: dict[str, bool] = {}

        for commit in commits:
            msg_lower = commit.message.lower()
            is_bug = any(kw in msg_lower for kw in cls.BUG_KEYWORDS)
            is_bug_commit_cache[commit.hash] = is_bug

            author_key = commit.author_email or commit.author_name

            # Author-level stats
            author_commits[author_key] += 1
            if is_bug:
                author_bug_commits[author_key] += 1

            # Parse commit date for velocity
            week_key = cls._to_week_key(commit.date)
            weekly_commits[week_key] += 1

            # File-level stats
            file_paths = [
                fc["path"] for fc in commit.files_changed
                if fc.get("path")
            ]

            for fc in commit.files_changed:
                path = str(fc.get("path") or "")
                if not path:
                    continue

                adds = int(fc.get("additions") or 0)
                dels = int(fc.get("deletions") or 0)

                file_commit_count[path] += 1
                file_additions[path] += adds
                file_deletions[path] += dels
                file_authors[path].add(author_key)
                author_files[author_key].add(path)
                author_additions[author_key] += adds
                author_deletions[author_key] += dels

                if is_bug:
                    file_bug_commits[path] += 1

            # Co-change pairs (files changed together)
            if len(file_paths) >= 2:
                for i in range(len(file_paths)):
                    for j in range(i + 1, min(i + 6, len(file_paths))):
                        pair = tuple(sorted([file_paths[i], file_paths[j]]))
                        co_change_pairs[pair] += 1

        # ── Build hotspot list ─────────────────────────────────────
        hotspots: list[dict[str, Any]] = []
        for path, count in file_commit_count.most_common(50):
            churn = file_additions[path] + file_deletions[path]
            hotspots.append({
                "file": path,
                "commit_count": count,
                "churn_lines": churn,
                "additions": file_additions[path],
                "deletions": file_deletions[path],
                "unique_authors": len(file_authors[path]),
                "bug_commit_count": file_bug_commits[path],
                "bug_ratio": round(
                    file_bug_commits[path] / max(count, 1), 3
                ),
                "hotspot_score": cls._hotspot_score(
                    count, churn, file_bug_commits[path]
                ),
            })

        # Sort by hotspot score
        hotspots.sort(key=lambda x: x["hotspot_score"], reverse=True)

        # ── Contributor stats ──────────────────────────────────────
        contributor_stats: list[dict[str, Any]] = []
        for author, commit_count in author_commits.most_common():
            contributor_stats.append({
                "author": author,
                "commit_count": commit_count,
                "files_touched": len(author_files[author]),
                "lines_added": author_additions[author],
                "lines_deleted": author_deletions[author],
                "bug_commits": author_bug_commits[author],
                "bug_ratio": round(
                    author_bug_commits[author] / max(commit_count, 1), 3
                ),
            })

        # ── Bug-prone files ────────────────────────────────────────
        bug_files: list[dict[str, Any]] = [
            {
                "file": path,
                "bug_commits": count,
                "total_commits": file_commit_count[path],
                "bug_ratio": round(count / max(file_commit_count[path], 1), 3),
            }
            for path, count in file_bug_commits.most_common(20)
            if count >= 2
        ]

        # ── Top co-change pairs ────────────────────────────────────
        co_changes: list[dict[str, Any]] = [
            {
                "file_a": pair[0],
                "file_b": pair[1],
                "co_change_count": count,
                "coupling_score": round(
                    count / max(
                        file_commit_count[pair[0]],
                        file_commit_count[pair[1]],
                        1,
                    ),
                    3,
                ),
            }
            for pair, count in co_change_pairs.most_common(20)
            if count >= 2
        ]
        co_changes.sort(key=lambda x: x["coupling_score"], reverse=True)

        # ── Velocity (weekly commit counts) ───────────────────────
        velocity: list[dict[str, Any]] = [
            {"week": week, "commits": count}
            for week, count in sorted(weekly_commits.items())
        ][-52:]  # Last 52 weeks

        # ── Summary ───────────────────────────────────────────────
        total_commits = len(commits)
        total_files = len(file_commit_count)
        bug_commits_total = sum(
            1 for c in commits
            if is_bug_commit_cache.get(c.hash, False)
        )

        return {
            "hotspots": hotspots,
            "contributor_stats": contributor_stats,
            "bug_files": bug_files,
            "co_changes": co_changes,
            "velocity": velocity,
            "summary": {
                "total_commits": total_commits,
                "total_files_changed": total_files,
                "total_contributors": len(author_commits),
                "bug_commits": bug_commits_total,
                "bug_commit_ratio": round(
                    bug_commits_total / max(total_commits, 1), 3
                ),
                "most_active_file": (
                    hotspots[0]["file"] if hotspots else None
                ),
                "most_active_author": (
                    contributor_stats[0]["author"]
                    if contributor_stats else None
                ),
                "date_range": cls._date_range(commits),
            },
        }

    @staticmethod
    def _hotspot_score(
        commit_count: int,
        churn_lines: int,
        bug_commits: int,
    ) -> float:
        """
        Calculate a composite hotspot score for ranking files.

        Formula weights commit frequency, churn size, and bug history.

        Args:
            commit_count: Times the file was committed
            churn_lines:  Total lines added + deleted
            bug_commits:  Number of bug-fix commits touching this file

        Returns:
            Float hotspot score (higher = more problematic)
        """
        # Normalize each factor (log scale to avoid outlier dominance)
        import math
        freq_score = math.log1p(commit_count) * 10
        churn_score = math.log1p(churn_lines)
        bug_score = bug_commits * 5
        return round(freq_score + churn_score + bug_score, 2)

    @staticmethod
    def _to_week_key(date_str: str) -> str:
        """
        Convert a date string to a YYYY-WW week key.

        Args:
            date_str: Date string in various formats

        Returns:
            Week key string e.g. "2024-W03"
        """
        try:
            # Try ISO format: "2024-01-15 10:30:00 +0000"
            clean = date_str.split("+")[0].split("-0")[0].strip()
            dt = datetime.fromisoformat(clean)
            return dt.strftime("%Y-W%V")
        except Exception:
            try:
                # Try just the date part
                parts = date_str.split()
                if parts:
                    dt = datetime.strptime(parts[0], "%Y-%m-%d")
                    return dt.strftime("%Y-W%V")
            except Exception:
                pass
        return "unknown"

    @staticmethod
    def _date_range(commits: list[GitCommit]) -> dict[str, str]:
        """
        Extract earliest and latest commit dates.

        Args:
            commits: List of GitCommit objects

        Returns:
            Dict with earliest and latest date strings
        """
        if not commits:
            return {"earliest": "", "latest": ""}
        dates = [c.date for c in commits if c.date]
        return {
            "earliest": min(dates) if dates else "",
            "latest": max(dates) if dates else "",
        }


# =============================================================================
# Blame Analyzer
# =============================================================================

class BlameAnalyzer:
    """
    Analyzes git blame output to compute line ownership statistics.

    Accepts pre-parsed blame data (list of line dicts) since running
    git blame on the server requires the git repository to be present.
    """

    @staticmethod
    def analyze(blame_lines: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Analyze blame data and return ownership statistics.

        Args:
            blame_lines: List of line dicts with keys:
                hash, author, date, line_number, content

        Returns:
            Dict with author_ownership, age_distribution, stale_lines
        """
        if not blame_lines:
            return {
                "total_lines": 0,
                "author_ownership": [],
                "avg_line_age_days": 0.0,
                "stale_lines": 0,
                "stale_ratio": 0.0,
            }

        now = datetime.now(timezone.utc)
        author_lines: Counter = Counter()
        line_ages: list[float] = []
        stale_count = 0
        stale_threshold_days = 365

        for line in blame_lines:
            author = str(line.get("author") or "unknown")
            date_str = str(line.get("date") or "")
            author_lines[author] += 1

            # Calculate line age
            try:
                clean_date = date_str.split("+")[0].strip()
                line_date = datetime.fromisoformat(clean_date)
                if line_date.tzinfo is None:
                    line_date = line_date.replace(tzinfo=timezone.utc)
                age_days = (now - line_date).days
                line_ages.append(float(age_days))
                if age_days > stale_threshold_days:
                    stale_count += 1
            except Exception:
                line_ages.append(0.0)

        total = len(blame_lines)
        avg_age = round(sum(line_ages) / max(len(line_ages), 1), 1)

        # Author ownership breakdown
        author_ownership: list[dict[str, Any]] = [
            {
                "author": author,
                "lines": count,
                "percentage": round(count / max(total, 1) * 100, 1),
            }
            for author, count in author_lines.most_common()
        ]

        return {
            "total_lines": total,
            "author_ownership": author_ownership,
            "avg_line_age_days": avg_age,
            "stale_lines": stale_count,
            "stale_ratio": round(stale_count / max(total, 1), 3),
        }


# =============================================================================
# Main Git Analyzer
# =============================================================================

class GitAnalyzer:
    """
    Main entry point for git history analysis.

    Orchestrates GitLogParser, HotspotAnalyzer, and BlameAnalyzer
    into a unified analysis pipeline.
    """

    def __init__(self) -> None:
        """Initialize with stateless sub-analyzers."""
        self._hotspot = HotspotAnalyzer()

    def analyze_commits(
        self,
        commits: list[dict[str, Any]],
        top_hotspots: int = 20,
    ) -> dict[str, Any]:
        """
        Analyze a list of commit dicts and return full git history analysis.

        Args:
            commits:      List of commit dicts (API input format)
            top_hotspots: Number of hotspot files to return

        Returns:
            Complete git analysis dict with hotspots, contributors,
            bug files, co-changes, velocity, and summary
        """
        parsed = GitLogParser.parse_from_dicts(commits)
        result = HotspotAnalyzer.analyze(parsed)

        # Truncate to requested top N
        result["hotspots"] = result["hotspots"][:top_hotspots]

        return result

    def analyze_raw_log(
        self,
        raw_log: str,
        top_hotspots: int = 20,
    ) -> dict[str, Any]:
        """
        Analyze raw git log string output.

        Args:
            raw_log:      Raw git log --numstat output
            top_hotspots: Number of hotspot files to return

        Returns:
            Complete git analysis dict
        """
        parsed = GitLogParser.parse(raw_log)
        result = HotspotAnalyzer.analyze(parsed)
        result["hotspots"] = result["hotspots"][:top_hotspots]
        return result

    def analyze_blame(
        self,
        blame_lines: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Analyze git blame data for a single file.

        Args:
            blame_lines: List of blame line dicts

        Returns:
            Blame analysis dict with ownership and age stats
        """
        return BlameAnalyzer.analyze(blame_lines)

    def get_file_history(
        self,
        commits: list[dict[str, Any]],
        file_path: str,
    ) -> dict[str, Any]:
        """
        Get commit history for a specific file.

        Args:
            commits:   Full commit list
            file_path: File path to filter for

        Returns:
            Dict with commits touching this file,
            churn trend, and author breakdown
        """
        parsed = GitLogParser.parse_from_dicts(commits)

        file_commits: list[dict[str, Any]] = []
        author_counter: Counter = Counter()
        weekly_churn: dict[str, int] = defaultdict(int)

        for commit in parsed:
            for fc in commit.files_changed:
                if fc.get("path") == file_path:
                    author_counter[commit.author_email or commit.author_name] += 1
                    churn = int(fc.get("additions") or 0) + int(fc.get("deletions") or 0)
                    week = HotspotAnalyzer._to_week_key(commit.date)
                    weekly_churn[week] += churn

                    file_commits.append({
                        "hash": commit.hash,
                        "author": commit.author_name,
                        "date": commit.date,
                        "message": commit.message,
                        "additions": fc.get("additions", 0),
                        "deletions": fc.get("deletions", 0),
                    })

        return {
            "file_path": file_path,
            "total_commits": len(file_commits),
            "commits": file_commits[:50],
            "authors": [
                {"author": a, "commits": c}
                for a, c in author_counter.most_common()
            ],
            "weekly_churn": [
                {"week": w, "churn": c}
                for w, c in sorted(weekly_churn.items())
            ][-26:],
        }
