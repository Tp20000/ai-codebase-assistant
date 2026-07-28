"""
Step 35 Test Suite - Language Detection and Routing
Run from backend/ directory:
    cd backend
    python test_language_detector.py
"""

import sys
import traceback

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


# ---------------------------------------------------------------------------
def test_extension_detection() -> None:
    print("[1] Extension-based detection")
    from app.core.parsers.language_detector import LanguageDetector

    cases = [
        ("main.py",          "python"),
        ("app.js",           "javascript"),
        ("index.tsx",        "typescript"),
        ("Main.java",        "java"),
        ("main.go",          "go"),
        ("lib.rs",           "rust"),
        ("app.cpp",          "cpp"),
        ("Program.cs",       "csharp"),
        ("style.css",        "css"),
        ("query.sql",        "sql"),
        ("config.yaml",      "yaml"),
        ("config.yml",       "yaml"),
        ("data.json",        "json"),
        ("README.md",        "markdown"),
        ("script.rb",        "ruby"),
        ("index.php",        "php"),
        ("main.swift",       "swift"),
        ("App.kt",           "kotlin"),
    ]

    for path, expected in cases:
        result = LanguageDetector.detect(path)
        assert result["language_id"] == expected, \
            f"detect('{path}') = '{result['language_id']}', expected '{expected}'"
        assert result["confidence"] == "high"
        assert result["method"] == "extension"

    print(f"  {len(cases)} extension cases all correct")
    ok("extension detection")


# ---------------------------------------------------------------------------
def test_filename_detection() -> None:
    print("[2] Filename-based detection")
    from app.core.parsers.language_detector import LanguageDetector

    cases = [
        ("Makefile",        "makefile"),
        ("Dockerfile",      "docker"),
        ("Gemfile",         "ruby"),
        ("Vagrantfile",     "ruby"),
        (".gitignore",      "gitignore"),
        (".env",            "env"),
        ("package.json",    "json"),
        ("go.mod",          "go"),
        ("Cargo.toml",      "toml"),
    ]

    for filename, expected in cases:
        result = LanguageDetector.detect(filename)
        assert result["language_id"] == expected, \
            f"detect('{filename}') = '{result['language_id']}', expected '{expected}'"
        assert result["method"] == "filename"

    print(f"  {len(cases)} filename cases all correct")
    ok("filename detection")


# ---------------------------------------------------------------------------
def test_shebang_detection() -> None:
    print("[3] Shebang line detection")
    from app.core.parsers.language_detector import ShebangDetector, LanguageDetector

    shebang_cases = [
        ("#!/usr/bin/env python3",   "python"),
        ("#!/usr/bin/env python",    "python"),
        ("#!/usr/bin/python3",       "python"),
        ("#!/usr/bin/env node",      "javascript"),
        ("#!/usr/bin/env ruby",      "ruby"),
        ("#!/bin/bash",              "bash"),
        ("#!/usr/bin/env bash",      "bash"),
        ("#!/usr/bin/env perl",      "perl"),
        ("#!/usr/bin/env lua",       "lua"),
    ]

    for shebang, expected in shebang_cases:
        result = ShebangDetector.detect(shebang)
        assert result == expected, \
            f"ShebangDetector('{shebang}') = '{result}', expected '{expected}'"
        print(f"  {shebang[:40]} -> {result}")

    # Test via LanguageDetector (extensionless file with shebang)
    result = LanguageDetector.detect(
        "myscript",
        content="#!/usr/bin/env python3\n\nprint('hello')\n",
    )
    assert result["language_id"] == "python"
    assert result["method"] == "shebang"

    ok("shebang detection")


# ---------------------------------------------------------------------------
def test_content_heuristics_python() -> None:
    print("[4] Content heuristics - Python")
    from app.core.parsers.language_detector import LanguageDetector

    py_code = (
        "import os\n"
        "from pathlib import Path\n\n"
        "def calculate(x: int, y: int) -> int:\n"
        '    """Calculate sum."""\n'
        "    return x + y\n\n"
        "class MyClass:\n"
        "    def __init__(self):\n"
        "        self.value = 42\n\n"
        "if __name__ == '__main__':\n"
        "    print(calculate(1, 2))\n"
    )

    result = LanguageDetector.detect("unknown_file", py_code)
    print(f"  Detected: {result['language_id']} (confidence: {result['confidence']})")
    assert result["language_id"] == "python"
    assert result["confidence"] in ("high", "medium")
    assert result["method"] == "heuristics"

    ok("heuristics Python")


# ---------------------------------------------------------------------------
def test_content_heuristics_javascript() -> None:
    print("[5] Content heuristics - JavaScript")
    from app.core.parsers.language_detector import LanguageDetector

    js_code = (
        "const express = require('express');\n"
        "const app = express();\n\n"
        "function handleRequest(req, res) {\n"
        "    console.log('Request received');\n"
        "    const data = req.body;\n"
        "    res.json({ status: 'ok', data });\n"
        "}\n\n"
        "module.exports = { handleRequest };\n"
    )

    result = LanguageDetector.detect("unknown_file", js_code)
    print(f"  Detected: {result['language_id']} (confidence: {result['confidence']})")
    assert result["language_id"] == "javascript"

    ok("heuristics JavaScript")


# ---------------------------------------------------------------------------
def test_content_heuristics_typescript() -> None:
    print("[6] Content heuristics - TypeScript")
    from app.core.parsers.language_detector import LanguageDetector

    ts_code = (
        "interface UserData {\n"
        "    id: number;\n"
        "    name: string;\n"
        "    email: string;\n"
        "}\n\n"
        "type ApiResponse<T> = {\n"
        "    data: T;\n"
        "    error: string | null;\n"
        "};\n\n"
        "async function fetchUser(id: number): Promise<UserData> {\n"
        "    const response = await fetch(`/api/users/${id}`);\n"
        "    return response.json() as UserData;\n"
        "}\n"
    )

    result = LanguageDetector.detect("unknown_file", ts_code)
    print(f"  Detected: {result['language_id']} (confidence: {result['confidence']})")
    assert result["language_id"] == "typescript"

    ok("heuristics TypeScript")


# ---------------------------------------------------------------------------
def test_content_heuristics_java() -> None:
    print("[7] Content heuristics - Java")
    from app.core.parsers.language_detector import LanguageDetector

    java_code = (
        "import java.util.List;\n"
        "import org.springframework.stereotype.Service;\n\n"
        "@Service\n"
        "public class UserService {\n"
        "    private final UserRepository repo;\n\n"
        "    public UserService(UserRepository repo) {\n"
        "        this.repo = repo;\n"
        "    }\n\n"
        "    public static void main(String[] args) {\n"
        "        System.out.println(\"Hello World\");\n"
        "    }\n"
        "}\n"
    )

    result = LanguageDetector.detect("unknown_file", java_code)
    print(f"  Detected: {result['language_id']} (confidence: {result['confidence']})")
    assert result["language_id"] == "java"

    ok("heuristics Java")


# ---------------------------------------------------------------------------
def test_language_info_completeness() -> None:
    print("[8] LanguageInfo metadata completeness")
    from app.core.parsers.language_detector import LANGUAGES

    required_langs = ["python", "javascript", "typescript", "java",
                      "go", "rust", "cpp", "csharp", "ruby", "php"]

    for lang_id in required_langs:
        assert lang_id in LANGUAGES, f"Missing language: {lang_id}"
        info = LANGUAGES[lang_id]
        assert info.display_name, f"{lang_id} missing display_name"
        assert info.extensions, f"{lang_id} missing extensions"
        assert info.comment_single is not None, f"{lang_id} missing comment_single"
        assert info.test_frameworks, f"{lang_id} missing test_frameworks"
        assert info.color.startswith("#"), f"{lang_id} color must be hex"
        d = info.to_dict()
        assert "id" in d and "display_name" in d and "color" in d

    print(f"  {len(required_langs)} languages all have complete metadata")
    ok("language metadata completeness")


# ---------------------------------------------------------------------------
def test_extension_map_coverage() -> None:
    print("[9] Extension map coverage")
    from app.core.parsers.language_detector import EXTENSION_MAP

    required_extensions = [
        ".py", ".js", ".ts", ".tsx", ".jsx",
        ".java", ".go", ".rs", ".cpp", ".cs",
        ".rb", ".php", ".swift", ".kt",
        ".sql", ".yaml", ".yml", ".json", ".md",
        ".sh", ".html", ".css", ".toml",
    ]

    for ext in required_extensions:
        assert ext in EXTENSION_MAP, f"Missing extension: {ext}"

    print(f"  {len(EXTENSION_MAP)} total extensions mapped")
    print(f"  Required {len(required_extensions)} all present")
    ok("extension map coverage")


# ---------------------------------------------------------------------------
def test_language_router() -> None:
    print("[10] LanguageRouter routing table")
    from app.core.parsers.language_detector import LanguageRouter

    test_cases = [
        ("python", "ast", "by_function", "pytest"),
        ("javascript", "regex", "by_function", "jest"),
        ("typescript", "regex", "by_function", "jest"),
        ("java", "regex", "by_class", "junit"),
        ("go", "regex", "by_function", "go_test"),
        ("rust", "regex", "by_function", "cargo_test"),
        ("unknown_lang", "generic", "by_lines", "generic"),
    ]

    for lang, parser, chunking, test_format in test_cases:
        route = LanguageRouter.route(lang)
        assert route["parser"] == parser, \
            f"{lang}: parser={route['parser']}, expected={parser}"
        assert route["chunking"] == chunking, \
            f"{lang}: chunking={route['chunking']}, expected={chunking}"
        assert route["test_format"] == test_format, \
            f"{lang}: test_format={route['test_format']}, expected={test_format}"
        print(f"  {lang:12s} -> parser={parser} chunking={chunking}")

    ok("language router")


# ---------------------------------------------------------------------------
def test_prompt_context() -> None:
    print("[11] Language prompt context for agents")
    from app.core.parsers.language_detector import LanguageRouter

    py_ctx = LanguageRouter.get_system_prompt_context("python")
    print(f"  Python context: {py_ctx}")
    assert py_ctx["language"] == "Python"
    assert py_ctx["comment_single"] == "#"
    assert py_ctx["doc_style"] == "google"
    assert "snake_case" in py_ctx["naming_conventions"]
    assert "pytest" in py_ctx["test_framework"]

    js_ctx = LanguageRouter.get_system_prompt_context("javascript")
    assert js_ctx["comment_single"] == "//"
    assert js_ctx["doc_style"] == "jsdoc"

    # Unknown language should return default context
    unknown_ctx = LanguageRouter.get_system_prompt_context("brainfuck")
    assert unknown_ctx["language"] == "brainfuck"
    assert "comment_style" in unknown_ctx

    ok("prompt context generation")


# ---------------------------------------------------------------------------
def test_batch_detection() -> None:
    print("[12] Batch detection and project stats")
    from app.core.parsers.language_detector import LanguageDetector

    files = [
        {"path": "app/main.py", "content": "import os\ndef main(): pass"},
        {"path": "app/utils.py", "content": "def helper(): return 42"},
        {"path": "app/models.py", "content": "class User: pass"},
        {"path": "src/App.tsx", "content": "import React from 'react';\ninterface Props { id: number; }"},
        {"path": "src/utils.ts", "content": "type Result = string | number;"},
        {"path": "README.md", "content": "# My Project\n\nDescription here."},
        {"path": "package.json", "content": '{"name": "myapp"}'},
        {"path": "Dockerfile", "content": "FROM python:3.12"},
    ]

    detections = LanguageDetector.detect_batch(files)
    print(f"  Detected {len(detections)} files:")
    for d in detections:
        print(f"    {d['file_path']:30s} -> {d['language_id']:12s} ({d['method']})")

    assert len(detections) == 8
    py_dets = [d for d in detections if d["language_id"] == "python"]
    ts_dets = [d for d in detections if d["language_id"] == "typescript"]
    assert len(py_dets) == 3
    assert len(ts_dets) >= 1

    # Project stats
    stats = LanguageDetector.get_project_language_stats(files)
    print(f"\n  Project stats:")
    print(f"    Primary: {stats['primary_language']}")
    print(f"    Is polyglot: {stats['is_polyglot']}")
    print(f"    Languages: {[b['language_id'] for b in stats['breakdown'][:4]]}")

    assert stats["primary_language"] == "python"  # 3 py files > 2 ts files
    assert stats["is_polyglot"] is True
    assert stats["total_files"] == 8

    ok("batch detection and project stats")


# ---------------------------------------------------------------------------
def test_unknown_file() -> None:
    print("[13] Unknown file detection")
    from app.core.parsers.language_detector import LanguageDetector

    result = LanguageDetector.detect("file.xyz", "x = 1 // simple")
    print(f"  Unknown file: {result}")
    assert result["language_id"] in ("unknown", "javascript")  # '//' triggers JS
    assert result["confidence"] in ("none", "low")

    # Empty content extensionless file
    result2 = LanguageDetector.detect("UNKNOWN_FILE", "")
    assert result2["language_id"] == "unknown"
    assert result2["confidence"] == "none"

    ok("unknown file detection")


# ---------------------------------------------------------------------------
def test_analytics_api_has_language() -> None:
    print("[14] analytics.py has language detection endpoints")
    with open("app/api/v1/analytics.py", "r", encoding="utf-8") as f:
        content = f.read()

    assert "/language/detect" in content
    assert "/language/supported" in content
    print(f"  Language endpoints: {content.count('/language/')}")

    ok("analytics.py has language endpoints")


# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 60)
    print("Step 35 - Language Detection and Routing Test Suite")
    print("=" * 60)
    print()

    tests = [
        test_extension_detection,
        test_filename_detection,
        test_shebang_detection,
        test_content_heuristics_python,
        test_content_heuristics_javascript,
        test_content_heuristics_typescript,
        test_content_heuristics_java,
        test_language_info_completeness,
        test_extension_map_coverage,
        test_language_router,
        test_prompt_context,
        test_batch_detection,
        test_unknown_file,
        test_analytics_api_has_language,
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
        print("Language detection system ready!")
        print()
        print("API endpoints added:")
        print("  POST /api/v1/analytics/language/detect")
        print("  POST /api/v1/analytics/language/detect-batch")
        print("  GET  /api/v1/analytics/language/supported")

    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
