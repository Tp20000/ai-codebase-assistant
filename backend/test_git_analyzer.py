"""
Step 34 Test Suite - Git History Analyzer
Run from backend/ directory:
    cd backend
    python test_git_analyzer.py
"""

import sys
import traceback
from datetime import datetime, timezone, timedelta

sys.path.insert(0, ".")

PASS = 0
FAIL = 0


def ok(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  PASS: {label}")


def fail(label: str, exc: Exception) -> None:
    global FAIL
    FAIL += 1
    print(f"  FAIL: {label} -> {exc}")
    traceback.print_exc()


def make_commit(
    hash_val: str,
    author: str = "dev@example.com",
    name: str = "Developer",
    date: str = "2024-01-15 10:00:00 +0000",
    message: str = "Add feature",
    files: list | None = None,
) -> dict:
    """Helper to create a commit dict."""
    return {
        "hash": hash_val,
        "author_email": author,
        "author_name": name,
        "date": date,
        "message": message,
        "files_changed": files or [],
    }


# ---------------------------------------------------------------------------
def test_git_log_parser_raw() -> None:
    print("[1] GitLogParser.parse - raw log string")
    from app.core.parsers.git_analyzer import GitLogParser

    raw_log = (
        "abc1234|alice@example.com|Alice|2024-01-15 10:00:00 +0000|Fix login bug\n"
        "5\t2\tsrc/auth/login.py\n"
        "10\t3\tsrc/utils/helpers.py\n"
        "\n"
        "def5678|bob@example.com|Bob|2024-01-14 09:00:00 +0000|Add user service\n"
        "20\t0\tsrc/services/user.py\n"
        "3\t1\tsrc/models/user.py\n"
    )

    commits = GitLogParser.parse(raw_log)
    print(f"  Parsed {len(commits)} commits")
    assert len(commits) == 2

    c1 = commits[0]
    assert c1.hash == "abc1234"
    assert c1.author_email == "alice@example.com"
    assert "Fix login bug" in c1.message
    assert len(c1.files_changed) == 2
    assert c1.files_changed[0]["path"] == "src/auth/login.py"
    assert c1.files_changed[0]["additions"] == 5
    assert c1.files_changed[0]["deletions"] == 2

    c2 = commits[1]
    assert c2.author_name == "Bob"
    assert len(c2.files_changed) == 2

    ok("GitLogParser raw log")


# ---------------------------------------------------------------------------
def test_git_log_parser_dicts() -> None:
    print("[2] GitLogParser.parse_from_dicts")
    from app.core.parsers.git_analyzer import GitLogParser

    commit_dicts = [
        make_commit("hash1", files=[
            {"path": "app/main.py", "additions": 10, "deletions": 2},
            {"path": "app/utils.py", "additions": 5, "deletions": 1},
        ]),
        make_commit("hash2", message="Fix critical bug", files=[
            {"path": "app/main.py", "additions": 3, "deletions": 8},
        ]),
    ]

    commits = GitLogParser.parse_from_dicts(commit_dicts)
    print(f"  Parsed {len(commits)} commits")
    assert len(commits) == 2
    assert commits[0].hash == "hash1"
    assert len(commits[0].files_changed) == 2
    assert commits[1].message == "Fix critical bug"

    ok("GitLogParser from dicts")


# ---------------------------------------------------------------------------
def test_hotspot_analyzer_basic() -> None:
    print("[3] HotspotAnalyzer - basic hotspot detection")
    from app.core.parsers.git_analyzer import GitLogParser, HotspotAnalyzer

    # main.py changed 5 times, utils.py changed 2 times
    commits = [
        make_commit(f"h{i}", files=[
            {"path": "app/main.py", "additions": 10, "deletions": 2},
        ])
        for i in range(5)
    ] + [
        make_commit(f"u{i}", files=[
            {"path": "app/utils.py", "additions": 5, "deletions": 1},
        ])
        for i in range(2)
    ]

    parsed = GitLogParser.parse_from_dicts(commits)
    result = HotspotAnalyzer.analyze(parsed)

    print(f"  Hotspots: {[h['file'] for h in result['hotspots'][:3]]}")
    assert len(result["hotspots"]) >= 2
    assert result["hotspots"][0]["file"] == "app/main.py"
    assert result["hotspots"][0]["commit_count"] == 5
    assert result["hotspots"][1]["file"] == "app/utils.py"

    ok("HotspotAnalyzer basic")


# ---------------------------------------------------------------------------
def test_bug_commit_detection() -> None:
    print("[4] Bug commit detection")
    from app.core.parsers.git_analyzer import GitLogParser, HotspotAnalyzer

    commits = [
        make_commit("h1", message="Fix null pointer exception", files=[
            {"path": "auth.py", "additions": 3, "deletions": 1},
        ]),
        make_commit("h2", message="Bug: login fails on mobile", files=[
            {"path": "auth.py", "additions": 5, "deletions": 2},
            {"path": "session.py", "additions": 2, "deletions": 0},
        ]),
        make_commit("h3", message="Add new feature", files=[
            {"path": "features.py", "additions": 20, "deletions": 0},
        ]),
        make_commit("h4", message="Error handling improvement", files=[
            {"path": "auth.py", "additions": 8, "deletions": 3},
        ]),
    ]

    parsed = GitLogParser.parse_from_dicts(commits)
    result = HotspotAnalyzer.analyze(parsed)

    print(f"  Bug files: {[f['file'] for f in result['bug_files']]}")
    print(f"  Bug commits total: {result['summary']['bug_commits']}")

    assert result["summary"]["bug_commits"] == 3  # h1, h2, h4 are bug commits
    assert any(f["file"] == "auth.py" for f in result["bug_files"])

    auth_hotspot = next(
        h for h in result["hotspots"] if h["file"] == "auth.py"
    )
    assert auth_hotspot["bug_commit_count"] >= 2
    assert auth_hotspot["bug_ratio"] > 0.5

    ok("bug commit detection")


# ---------------------------------------------------------------------------
def test_contributor_stats() -> None:
    print("[5] Contributor statistics")
    from app.core.parsers.git_analyzer import GitLogParser, HotspotAnalyzer

    commits = [
        make_commit("h1", author="alice@co.com", name="Alice", files=[
            {"path": "main.py", "additions": 50, "deletions": 10},
        ]),
        make_commit("h2", author="alice@co.com", name="Alice", files=[
            {"path": "utils.py", "additions": 30, "deletions": 5},
        ]),
        make_commit("h3", author="bob@co.com", name="Bob",
                    message="Fix crash", files=[
            {"path": "main.py", "additions": 5, "deletions": 20},
        ]),
    ]

    parsed = GitLogParser.parse_from_dicts(commits)
    result = HotspotAnalyzer.analyze(parsed)

    print(f"  Contributors: {[c['author'] for c in result['contributor_stats']]}")

    assert len(result["contributor_stats"]) == 2
    alice = next(c for c in result["contributor_stats"]
                 if "alice" in c["author"])
    bob = next(c for c in result["contributor_stats"]
               if "bob" in c["author"])

    assert alice["commit_count"] == 2
    assert alice["files_touched"] == 2
    assert alice["lines_added"] == 80
    assert bob["commit_count"] == 1
    assert bob["bug_commits"] == 1

    ok("contributor statistics")


# ---------------------------------------------------------------------------
def test_co_change_detection() -> None:
    print("[6] Co-change pair detection")
    from app.core.parsers.git_analyzer import GitLogParser, HotspotAnalyzer

    # auth.py and session.py always change together
    commits = [
        make_commit(f"h{i}", files=[
            {"path": "auth.py", "additions": 5, "deletions": 1},
            {"path": "session.py", "additions": 3, "deletions": 0},
        ])
        for i in range(5)
    ] + [
        make_commit("solo", files=[
            {"path": "readme.py", "additions": 1, "deletions": 0},
        ]),
    ]

    parsed = GitLogParser.parse_from_dicts(commits)
    result = HotspotAnalyzer.analyze(parsed)

    print(f"  Co-change pairs: {result['co_changes'][:3]}")
    assert len(result["co_changes"]) >= 1
    top_pair = result["co_changes"][0]
    assert "auth.py" in [top_pair["file_a"], top_pair["file_b"]]
    assert "session.py" in [top_pair["file_a"], top_pair["file_b"]]
    assert top_pair["co_change_count"] == 5
    assert top_pair["coupling_score"] == 1.0

    ok("co-change pair detection")


# ---------------------------------------------------------------------------
def test_velocity_calculation() -> None:
    print("[7] Commit velocity (weekly buckets)")
    from app.core.parsers.git_analyzer import GitLogParser, HotspotAnalyzer

    # Commits spread across multiple weeks
    commits = [
        make_commit(f"h{i}", date=f"2024-0{1 + i//3}-{(i%3+1)*7:02d} 10:00:00 +0000")
        for i in range(9)
    ]

    parsed = GitLogParser.parse_from_dicts(commits)
    result = HotspotAnalyzer.analyze(parsed)

    print(f"  Velocity entries: {len(result['velocity'])}")
    print(f"  Weeks: {[v['week'] for v in result['velocity'][:5]]}")
    assert len(result["velocity"]) >= 1

    for v in result["velocity"]:
        assert "week" in v
        assert "commits" in v
        assert v["commits"] >= 1

    ok("velocity calculation")


# ---------------------------------------------------------------------------
def test_blame_analyzer() -> None:
    print("[8] BlameAnalyzer")
    from app.core.parsers.git_analyzer import BlameAnalyzer

    now = datetime.now(timezone.utc)
    old_date = (now - timedelta(days=400)).strftime("%Y-%m-%d %H:%M:%S")
    recent_date = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

    blame_lines = [
        {"author": "alice@co.com", "date": recent_date,
         "line_number": i, "content": f"line {i}"}
        for i in range(60)
    ] + [
        {"author": "bob@co.com", "date": old_date,
         "line_number": i + 60, "content": f"old line {i}"}
        for i in range(40)
    ]

    result = BlameAnalyzer.analyze(blame_lines)
    print(f"  Total lines: {result['total_lines']}")
    print(f"  Authors: {[a['author'] for a in result['author_ownership']]}")
    print(f"  Stale lines: {result['stale_lines']}")
    print(f"  Avg age: {result['avg_line_age_days']} days")

    assert result["total_lines"] == 100
    assert len(result["author_ownership"]) == 2

    alice = next(
        a for a in result["author_ownership"] if "alice" in a["author"]
    )
    assert alice["lines"] == 60
    assert alice["percentage"] == 60.0

    assert result["stale_lines"] == 40  # bob's old lines
    assert result["avg_line_age_days"] > 0

    ok("BlameAnalyzer")


# ---------------------------------------------------------------------------
def test_file_history() -> None:
    print("[9] GitAnalyzer.get_file_history")
    from app.core.parsers.git_analyzer import GitAnalyzer

    analyzer = GitAnalyzer()
    commits = [
        make_commit("h1", author="alice@co.com", name="Alice",
                    date="2024-01-10 10:00:00 +0000",
                    message="Add login", files=[
            {"path": "auth.py", "additions": 50, "deletions": 0},
        ]),
        make_commit("h2", author="bob@co.com", name="Bob",
                    date="2024-01-15 10:00:00 +0000",
                    message="Fix bug in auth", files=[
            {"path": "auth.py", "additions": 5, "deletions": 3},
            {"path": "utils.py", "additions": 2, "deletions": 0},
        ]),
        make_commit("h3", author="alice@co.com", name="Alice",
                    date="2024-01-20 10:00:00 +0000",
                    message="Refactor auth", files=[
            {"path": "auth.py", "additions": 20, "deletions": 30},
        ]),
    ]

    result = analyzer.get_file_history(commits, "auth.py")
    print(f"  Total commits for auth.py: {result['total_commits']}")
    print(f"  Authors: {[a['author'] for a in result['authors']]}")

    assert result["file_path"] == "auth.py"
    assert result["total_commits"] == 3
    assert len(result["authors"]) == 2
    assert result["authors"][0]["author"] == "alice@co.com"
    assert result["authors"][0]["commits"] == 2

    ok("GitAnalyzer.get_file_history")


# ---------------------------------------------------------------------------
def test_git_analyzer_full_pipeline() -> None:
    print("[10] GitAnalyzer.analyze_commits - full pipeline")
    from app.core.parsers.git_analyzer import GitAnalyzer

    analyzer = GitAnalyzer()

    # Realistic commit history
    commits = []
    files = [
        "src/auth/login.py",
        "src/auth/session.py",
        "src/api/routes.py",
        "src/models/user.py",
        "src/utils/helpers.py",
    ]

    import random
    random.seed(42)

    for i in range(30):
        is_bug = i % 4 == 0
        msg = f"Fix bug #{i}" if is_bug else f"Add feature #{i}"
        changed = random.sample(files, random.randint(1, 3))
        commits.append(make_commit(
            f"commit{i:04d}",
            author=f"dev{i % 3}@co.com",
            name=f"Developer {i % 3}",
            date=f"2024-{(i // 10) + 1:02d}-{(i % 28) + 1:02d} 10:00:00 +0000",
            message=msg,
            files=[
                {"path": p, "additions": random.randint(1, 50),
                 "deletions": random.randint(0, 20)}
                for p in changed
            ],
        ))

    result = analyzer.analyze_commits(commits, top_hotspots=5)

    print(f"  Total commits: {result['summary']['total_commits']}")
    print(f"  Total files: {result['summary']['total_files_changed']}")
    print(f"  Contributors: {result['summary']['total_contributors']}")
    print(f"  Bug commits: {result['summary']['bug_commits']}")
    print(f"  Top hotspot: {result['hotspots'][0]['file'] if result['hotspots'] else 'none'}")

    assert result["summary"]["total_commits"] == 30
    assert result["summary"]["total_contributors"] == 3
    assert len(result["hotspots"]) <= 5
    assert len(result["contributor_stats"]) == 3
    assert result["summary"]["bug_commits"] >= 5

    ok("full pipeline analysis")


# ---------------------------------------------------------------------------
def test_empty_commits() -> None:
    print("[11] Empty commit list")
    from app.core.parsers.git_analyzer import GitAnalyzer

    analyzer = GitAnalyzer()
    result = analyzer.analyze_commits([])
    print(f"  Summary: {result['summary']}")
    assert result["summary"]["total_commits"] == 0
    assert result["hotspots"] == []
    assert result["contributor_stats"] == []

    ok("empty commit list")


# ---------------------------------------------------------------------------
def test_hotspot_score() -> None:
    print("[12] Hotspot score ranking")
    from app.core.parsers.git_analyzer import HotspotAnalyzer

    # High commits + high churn + many bugs = highest score
    score_high = HotspotAnalyzer._hotspot_score(100, 5000, 20)
    score_med = HotspotAnalyzer._hotspot_score(20, 500, 3)
    score_low = HotspotAnalyzer._hotspot_score(3, 50, 0)

    print(f"  high: {score_high}")
    print(f"  med:  {score_med}")
    print(f"  low:  {score_low}")

    assert score_high > score_med > score_low
    assert score_low >= 0

    ok("hotspot score ranking")


# ---------------------------------------------------------------------------
def test_analytics_api_has_git() -> None:
    print("[13] analytics.py has git endpoints")
    with open("app/api/v1/analytics.py", "r", encoding="utf-8") as f:
        content = f.read()

    assert "/git/analyze" in content
    assert "/git/file-history" in content
    assert "/git/blame" in content
    print(f"  git endpoint count: {content.count('/git/')}")

    ok("analytics.py has git endpoints")


# ---------------------------------------------------------------------------
def test_raw_log_parsing() -> None:
    print("[14] Raw git log parsing end-to-end")
    from app.core.parsers.git_analyzer import GitAnalyzer

    raw_log = (
        "aaa111|carol@co.com|Carol|2024-03-01 09:00:00 +0000|Fix security issue\n"
        "12\t5\tsrc/auth/login.py\n"
        "3\t1\tsrc/auth/session.py\n"
        "\n"
        "bbb222|david@co.com|David|2024-03-02 14:00:00 +0000|Add dashboard\n"
        "100\t0\tsrc/pages/dashboard.py\n"
        "20\t5\tsrc/api/routes.py\n"
        "\n"
        "ccc333|carol@co.com|Carol|2024-03-03 11:00:00 +0000|Error: fix dashboard\n"
        "8\t15\tsrc/pages/dashboard.py\n"
    )

    analyzer = GitAnalyzer()
    result = analyzer.analyze_raw_log(raw_log)

    print(f"  Commits: {result['summary']['total_commits']}")
    print(f"  Files: {result['summary']['total_files_changed']}")
    print(f"  Bug commits: {result['summary']['bug_commits']}")

    assert result["summary"]["total_commits"] == 3
    assert result["summary"]["total_files_changed"] == 4
    assert result["summary"]["bug_commits"] == 2  # "Fix security" + "Error: fix"

    dashboard = next(
        (h for h in result["hotspots"]
         if h["file"] == "src/pages/dashboard.py"), None
    )
    assert dashboard is not None
    assert dashboard["commit_count"] == 2

    ok("raw git log end-to-end")


# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 60)
    print("Step 34 - Git History Analyzer Test Suite")
    print("=" * 60)
    print()

    tests = [
        test_git_log_parser_raw,
        test_git_log_parser_dicts,
        test_hotspot_analyzer_basic,
        test_bug_commit_detection,
        test_contributor_stats,
        test_co_change_detection,
        test_velocity_calculation,
        test_blame_analyzer,
        test_file_history,
        test_git_analyzer_full_pipeline,
        test_empty_commits,
        test_hotspot_score,
        test_analytics_api_has_git,
        test_raw_log_parsing,
    ]

    for fn in tests:
        try:
            fn()
        except Exception as exc:
            fail(fn.__name__, exc)
        print()

    print("=" * 60)
    print(f"Results: {PASS} passed | {FAIL} failed")
    print("ALL TESTS PASSED" if FAIL == 0 else "SOME TESTS FAILED")
    print("=" * 60)

    if FAIL == 0:
        print()
        print("Git history analyzer ready!")
        print()
        print("New API endpoints:")
        print("  POST /api/v1/analytics/git/analyze")
        print("  POST /api/v1/analytics/git/analyze-raw")
        print("  POST /api/v1/analytics/git/file-history")
        print("  POST /api/v1/analytics/git/blame")

    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
