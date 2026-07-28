"""
Language Detection and Routing System - Step 35
AI Codebase Assistant v2.0

Detects programming languages from:
    1. File extension (fastest, most reliable)
    2. Shebang line (#!/usr/bin/env python3)
    3. Content heuristics (syntax patterns, keywords)
    4. Filename patterns (Makefile, Dockerfile, .env)

Routes files to the correct:
    - Parser    (AST-based for Python, regex for JS/TS)
    - Analyzer  (complexity, dependency, security)
    - Prompt template (agent system prompts)
    - Chunking strategy (by function/class/module)

Language metadata includes:
    - Display name, family, paradigm
    - Comment syntax (single-line, multi-line)
    - String delimiters
    - Import syntax
    - Test frameworks
    - Package managers
    - Linters / formatters

Supports 30+ languages with full metadata for the 10 most common.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# =============================================================================
# Language Metadata
# =============================================================================

@dataclass
class LanguageInfo:
    """
    Complete metadata about a programming language.

    Used by parsers, agents, and prompt templates to
    correctly handle language-specific syntax and conventions.
    """
    id: str                          # e.g. "python"
    display_name: str                # e.g. "Python"
    family: str                      # e.g. "scripting", "systems", "jvm"
    paradigm: list[str]              # e.g. ["oop", "functional"]
    extensions: list[str]            # e.g. [".py", ".pyw"]
    comment_single: str              # e.g. "#"
    comment_multi_start: str         # e.g. '"""'
    comment_multi_end: str           # e.g. '"""'
    string_delimiters: list[str]     # e.g. ['"', "'", '"""']
    import_keywords: list[str]       # e.g. ["import", "from"]
    function_keywords: list[str]     # e.g. ["def", "async def"]
    class_keywords: list[str]        # e.g. ["class"]
    test_frameworks: list[str]       # e.g. ["pytest", "unittest"]
    package_managers: list[str]      # e.g. ["pip", "poetry"]
    linters: list[str]               # e.g. ["flake8", "pylint", "ruff"]
    formatters: list[str]            # e.g. ["black", "autopep8"]
    doc_style: str                   # e.g. "google", "jsdoc", "javadoc"
    typing: str                      # "static" | "dynamic" | "gradual"
    popular_frameworks: list[str]    # e.g. ["FastAPI", "Django"]
    color: str = "#000000"           # Hex color for UI display
    icon: str = "file"               # Icon name for UI

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-safe dict."""
        return {
            "id": self.id,
            "display_name": self.display_name,
            "family": self.family,
            "paradigm": self.paradigm,
            "extensions": self.extensions,
            "comment_single": self.comment_single,
            "import_keywords": self.import_keywords,
            "function_keywords": self.function_keywords,
            "class_keywords": self.class_keywords,
            "test_frameworks": self.test_frameworks,
            "package_managers": self.package_managers,
            "linters": self.linters,
            "formatters": self.formatters,
            "doc_style": self.doc_style,
            "typing": self.typing,
            "popular_frameworks": self.popular_frameworks,
            "color": self.color,
            "icon": self.icon,
        }


# =============================================================================
# Language Registry
# =============================================================================

LANGUAGES: dict[str, LanguageInfo] = {

    "python": LanguageInfo(
        id="python",
        display_name="Python",
        family="scripting",
        paradigm=["oop", "functional", "imperative"],
        extensions=[".py", ".pyw", ".pyi", ".pyx"],
        comment_single="#",
        comment_multi_start='"""',
        comment_multi_end='"""',
        string_delimiters=['"', "'", '"""', "'''"],
        import_keywords=["import", "from"],
        function_keywords=["def", "async def", "lambda"],
        class_keywords=["class"],
        test_frameworks=["pytest", "unittest", "nose2", "hypothesis"],
        package_managers=["pip", "poetry", "conda", "pipenv", "uv"],
        linters=["flake8", "pylint", "ruff", "mypy", "pyright"],
        formatters=["black", "autopep8", "yapf", "isort"],
        doc_style="google",
        typing="gradual",
        popular_frameworks=["FastAPI", "Django", "Flask", "SQLAlchemy",
                            "Celery", "Pydantic", "LangChain"],
        color="#3776AB",
        icon="python",
    ),

    "javascript": LanguageInfo(
        id="javascript",
        display_name="JavaScript",
        family="scripting",
        paradigm=["oop", "functional", "event-driven"],
        extensions=[".js", ".mjs", ".cjs", ".jsx"],
        comment_single="//",
        comment_multi_start="/*",
        comment_multi_end="*/",
        string_delimiters=['"', "'", "`"],
        import_keywords=["import", "require", "export"],
        function_keywords=["function", "=>", "async function"],
        class_keywords=["class"],
        test_frameworks=["jest", "mocha", "vitest", "jasmine", "cypress"],
        package_managers=["npm", "yarn", "pnpm", "bun"],
        linters=["eslint", "jshint", "standard"],
        formatters=["prettier", "rome", "biome"],
        doc_style="jsdoc",
        typing="dynamic",
        popular_frameworks=["React", "Vue", "Angular", "Express",
                            "Next.js", "Nest.js", "Vite"],
        color="#F7DF1E",
        icon="javascript",
    ),

    "typescript": LanguageInfo(
        id="typescript",
        display_name="TypeScript",
        family="scripting",
        paradigm=["oop", "functional", "event-driven"],
        extensions=[".ts", ".tsx", ".d.ts", ".mts", ".cts"],
        comment_single="//",
        comment_multi_start="/*",
        comment_multi_end="*/",
        string_delimiters=['"', "'", "`"],
        import_keywords=["import", "export", "require"],
        function_keywords=["function", "=>", "async function"],
        class_keywords=["class", "interface", "type", "enum"],
        test_frameworks=["jest", "vitest", "mocha", "playwright"],
        package_managers=["npm", "yarn", "pnpm", "bun"],
        linters=["eslint", "tslint", "biome"],
        formatters=["prettier", "rome", "biome"],
        doc_style="tsdoc",
        typing="static",
        popular_frameworks=["React", "Angular", "NestJS", "Next.js",
                            "Fastify", "tRPC", "Zod"],
        color="#3178C6",
        icon="typescript",
    ),

    "java": LanguageInfo(
        id="java",
        display_name="Java",
        family="jvm",
        paradigm=["oop", "imperative"],
        extensions=[".java"],
        comment_single="//",
        comment_multi_start="/*",
        comment_multi_end="*/",
        string_delimiters=['"'],
        import_keywords=["import", "package"],
        function_keywords=["public", "private", "protected", "static",
                           "void", "return"],
        class_keywords=["class", "interface", "abstract", "enum",
                        "record", "sealed"],
        test_frameworks=["JUnit", "TestNG", "Mockito", "AssertJ"],
        package_managers=["maven", "gradle"],
        linters=["checkstyle", "pmd", "spotbugs", "sonarqube"],
        formatters=["google-java-format", "intellij"],
        doc_style="javadoc",
        typing="static",
        popular_frameworks=["Spring Boot", "Quarkus", "Micronaut",
                            "Jakarta EE", "Hibernate"],
        color="#007396",
        icon="java",
    ),

    "go": LanguageInfo(
        id="go",
        display_name="Go",
        family="systems",
        paradigm=["imperative", "concurrent"],
        extensions=[".go"],
        comment_single="//",
        comment_multi_start="/*",
        comment_multi_end="*/",
        string_delimiters=['"', "`"],
        import_keywords=["import", "package"],
        function_keywords=["func"],
        class_keywords=["type", "struct", "interface"],
        test_frameworks=["testing", "testify", "gomock", "ginkgo"],
        package_managers=["go mod", "dep"],
        linters=["golangci-lint", "staticcheck", "vet"],
        formatters=["gofmt", "goimports"],
        doc_style="godoc",
        typing="static",
        popular_frameworks=["Gin", "Echo", "Fiber", "Chi", "gRPC",
                            "GORM"],
        color="#00ADD8",
        icon="go",
    ),

    "rust": LanguageInfo(
        id="rust",
        display_name="Rust",
        family="systems",
        paradigm=["systems", "functional", "concurrent"],
        extensions=[".rs"],
        comment_single="//",
        comment_multi_start="/*",
        comment_multi_end="*/",
        string_delimiters=['"', "r#"],
        import_keywords=["use", "mod", "extern crate"],
        function_keywords=["fn", "async fn", "pub fn"],
        class_keywords=["struct", "enum", "trait", "impl"],
        test_frameworks=["cargo test", "proptest", "criterion"],
        package_managers=["cargo"],
        linters=["clippy", "rustfmt"],
        formatters=["rustfmt"],
        doc_style="rustdoc",
        typing="static",
        popular_frameworks=["Actix", "Axum", "Tokio", "Rocket",
                            "Serde", "Diesel"],
        color="#CE4A01",
        icon="rust",
    ),

    "cpp": LanguageInfo(
        id="cpp",
        display_name="C++",
        family="systems",
        paradigm=["oop", "systems", "functional"],
        extensions=[".cpp", ".cc", ".cxx", ".c++", ".hpp", ".h",
                    ".hxx", ".hh"],
        comment_single="//",
        comment_multi_start="/*",
        comment_multi_end="*/",
        string_delimiters=['"', "'"],
        import_keywords=["#include", "using namespace", "using"],
        function_keywords=["void", "int", "auto", "template",
                           "inline", "virtual"],
        class_keywords=["class", "struct", "namespace", "enum",
                        "template"],
        test_frameworks=["Google Test", "Catch2", "Boost.Test", "doctest"],
        package_managers=["conan", "vcpkg", "cmake"],
        linters=["clang-tidy", "cppcheck", "cpplint"],
        formatters=["clang-format"],
        doc_style="doxygen",
        typing="static",
        popular_frameworks=["Qt", "Boost", "POCO", "gRPC", "OpenCV"],
        color="#659BD3",
        icon="cpp",
    ),

    "csharp": LanguageInfo(
        id="csharp",
        display_name="C#",
        family="dotnet",
        paradigm=["oop", "functional", "imperative"],
        extensions=[".cs", ".csx"],
        comment_single="//",
        comment_multi_start="/*",
        comment_multi_end="*/",
        string_delimiters=['"', "@\"", "$\""],
        import_keywords=["using", "namespace"],
        function_keywords=["public", "private", "protected", "static",
                           "async", "void", "return"],
        class_keywords=["class", "interface", "struct", "record",
                        "enum", "abstract", "sealed"],
        test_frameworks=["xUnit", "NUnit", "MSTest", "Moq"],
        package_managers=["nuget", "dotnet"],
        linters=["roslyn", "sonarqube", "stylecop"],
        formatters=["dotnet format", "resharper"],
        doc_style="xmldoc",
        typing="static",
        popular_frameworks=["ASP.NET Core", "Entity Framework",
                            "Blazor", "MAUI", "SignalR"],
        color="#239120",
        icon="csharp",
    ),

    "kotlin": LanguageInfo(
        id="kotlin",
        display_name="Kotlin",
        family="jvm",
        paradigm=["oop", "functional"],
        extensions=[".kt", ".kts"],
        comment_single="//",
        comment_multi_start="/*",
        comment_multi_end="*/",
        string_delimiters=['"', '"""'],
        import_keywords=["import", "package"],
        function_keywords=["fun", "suspend fun"],
        class_keywords=["class", "data class", "sealed class",
                        "object", "interface", "enum class"],
        test_frameworks=["JUnit", "Kotest", "MockK", "Turbine"],
        package_managers=["maven", "gradle"],
        linters=["ktlint", "detekt"],
        formatters=["ktlint"],
        doc_style="kdoc",
        typing="static",
        popular_frameworks=["Spring Boot", "Ktor", "Jetpack Compose",
                            "Arrow", "Exposed"],
        color="#7F52FF",
        icon="kotlin",
    ),

    "ruby": LanguageInfo(
        id="ruby",
        display_name="Ruby",
        family="scripting",
        paradigm=["oop", "functional", "scripting"],
        extensions=[".rb", ".rake", ".gemspec"],
        comment_single="#",
        comment_multi_start="=begin",
        comment_multi_end="=end",
        string_delimiters=['"', "'", "%"],
        import_keywords=["require", "require_relative", "include",
                         "extend"],
        function_keywords=["def", "do", "lambda", "proc"],
        class_keywords=["class", "module"],
        test_frameworks=["RSpec", "Minitest", "Test::Unit"],
        package_managers=["gem", "bundler"],
        linters=["rubocop", "reek", "brakeman"],
        formatters=["rubocop", "standardrb"],
        doc_style="rdoc",
        typing="dynamic",
        popular_frameworks=["Rails", "Sinatra", "Hanami", "Grape"],
        color="#CC342D",
        icon="ruby",
    ),

    "php": LanguageInfo(
        id="php",
        display_name="PHP",
        family="scripting",
        paradigm=["oop", "scripting", "functional"],
        extensions=[".php", ".phtml", ".php3", ".php4", ".php5"],
        comment_single="//",
        comment_multi_start="/*",
        comment_multi_end="*/",
        string_delimiters=['"', "'"],
        import_keywords=["use", "namespace", "require", "include",
                         "require_once", "include_once"],
        function_keywords=["function", "fn"],
        class_keywords=["class", "interface", "trait", "abstract",
                        "final", "enum"],
        test_frameworks=["PHPUnit", "Pest", "Codeception"],
        package_managers=["composer"],
        linters=["phpstan", "psalm", "phpcs"],
        formatters=["php-cs-fixer", "phpcbf"],
        doc_style="phpdoc",
        typing="gradual",
        popular_frameworks=["Laravel", "Symfony", "WordPress",
                            "CodeIgniter", "Yii"],
        color="#777BB4",
        icon="php",
    ),

    "swift": LanguageInfo(
        id="swift",
        display_name="Swift",
        family="apple",
        paradigm=["oop", "functional", "protocol-oriented"],
        extensions=[".swift"],
        comment_single="//",
        comment_multi_start="/*",
        comment_multi_end="*/",
        string_delimiters=['"'],
        import_keywords=["import"],
        function_keywords=["func", "init", "deinit"],
        class_keywords=["class", "struct", "protocol", "enum",
                        "extension", "actor"],
        test_frameworks=["XCTest", "Swift Testing", "Quick/Nimble"],
        package_managers=["swift package manager", "cocoapods", "carthage"],
        linters=["swiftlint"],
        formatters=["swiftformat"],
        doc_style="markup",
        typing="static",
        popular_frameworks=["SwiftUI", "UIKit", "Vapor", "Combine"],
        color="#FA7343",
        icon="swift",
    ),

    "sql": LanguageInfo(
        id="sql",
        display_name="SQL",
        family="query",
        paradigm=["declarative", "relational"],
        extensions=[".sql", ".ddl", ".dml"],
        comment_single="--",
        comment_multi_start="/*",
        comment_multi_end="*/",
        string_delimiters=["'"],
        import_keywords=[],
        function_keywords=["FUNCTION", "PROCEDURE", "TRIGGER"],
        class_keywords=["TABLE", "VIEW", "INDEX", "SCHEMA"],
        test_frameworks=["pgTAP", "utPLSQL"],
        package_managers=[],
        linters=["sqlfluff", "sqllint"],
        formatters=["sqlfmt", "sqlformat"],
        doc_style="comment",
        typing="static",
        popular_frameworks=["PostgreSQL", "MySQL", "SQLite",
                            "SQL Server", "Oracle"],
        color="#336791",
        icon="sql",
    ),

    "markdown": LanguageInfo(
        id="markdown",
        display_name="Markdown",
        family="markup",
        paradigm=["declarative"],
        extensions=[".md", ".mdx", ".markdown"],
        comment_single="<!--",
        comment_multi_start="<!--",
        comment_multi_end="-->",
        string_delimiters=["`", "```"],
        import_keywords=[],
        function_keywords=[],
        class_keywords=[],
        test_frameworks=[],
        package_managers=[],
        linters=["markdownlint", "vale"],
        formatters=["prettier"],
        doc_style="markdown",
        typing="none",
        popular_frameworks=[],
        color="#083fa1",
        icon="markdown",
    ),

    "yaml": LanguageInfo(
        id="yaml",
        display_name="YAML",
        family="config",
        paradigm=["declarative"],
        extensions=[".yaml", ".yml"],
        comment_single="#",
        comment_multi_start="#",
        comment_multi_end="",
        string_delimiters=['"', "'", "|", ">"],
        import_keywords=[],
        function_keywords=[],
        class_keywords=[],
        test_frameworks=[],
        package_managers=[],
        linters=["yamllint", "prettier"],
        formatters=["prettier"],
        doc_style="comment",
        typing="dynamic",
        popular_frameworks=["Docker Compose", "Kubernetes",
                            "GitHub Actions", "Ansible"],
        color="#CB171E",
        icon="yaml",
    ),

    "json": LanguageInfo(
        id="json",
        display_name="JSON",
        family="config",
        paradigm=["declarative"],
        extensions=[".json", ".jsonc", ".json5"],
        comment_single="",
        comment_multi_start="",
        comment_multi_end="",
        string_delimiters=['"'],
        import_keywords=[],
        function_keywords=[],
        class_keywords=[],
        test_frameworks=[],
        package_managers=[],
        linters=["jsonlint", "prettier"],
        formatters=["prettier", "jq"],
        doc_style="none",
        typing="dynamic",
        popular_frameworks=["package.json", "tsconfig.json",
                            "OpenAPI", "JSON Schema"],
        color="#000000",
        icon="json",
    ),
}

# Extension to language ID map (fast lookup)
EXTENSION_MAP: dict[str, str] = {}
for lang_id, lang_info in LANGUAGES.items():
    for ext in lang_info.extensions:
        EXTENSION_MAP[ext.lower()] = lang_id

# Additional extensions for less common languages
EXTENSION_MAP.update({
    ".scala":  "scala",
    ".clj":    "clojure",
    ".ex":     "elixir",
    ".exs":    "elixir",
    ".hs":     "haskell",
    ".lhs":    "haskell",
    ".ml":     "ocaml",
    ".mli":    "ocaml",
    ".r":      "r",
    ".R":      "r",
    ".lua":    "lua",
    ".perl":   "perl",
    ".pl":     "perl",
    ".pm":     "perl",
    ".sh":     "bash",
    ".bash":   "bash",
    ".zsh":    "bash",
    ".fish":   "bash",
    ".ps1":    "powershell",
    ".psm1":   "powershell",
    ".dart":   "dart",
    ".vue":    "vue",
    ".svelte": "svelte",
    ".tf":     "terraform",
    ".hcl":    "terraform",
    ".toml":   "toml",
    ".ini":    "ini",
    ".env":    "env",
    ".css":    "css",
    ".scss":   "scss",
    ".sass":   "scss",
    ".less":   "less",
    ".html":   "html",
    ".htm":    "html",
    ".xml":    "xml",
    ".proto":  "protobuf",
    ".graphql": "graphql",
    ".gql":    "graphql",
    ".dockerfile": "docker",
    ".nix":    "nix",
    ".c":      "c",
})

# Filename patterns (no extension)
FILENAME_MAP: dict[str, str] = {
    "Makefile":        "makefile",
    "makefile":        "makefile",
    "GNUmakefile":     "makefile",
    "Dockerfile":      "docker",
    "dockerfile":      "docker",
    "Jenkinsfile":     "groovy",
    "Vagrantfile":     "ruby",
    "Gemfile":         "ruby",
    "Rakefile":        "ruby",
    "Guardfile":       "ruby",
    "Podfile":         "ruby",
    ".gitignore":      "gitignore",
    ".env":            "env",
    ".env.example":    "env",
    ".env.local":      "env",
    "requirements.txt": "text",
    "package.json":    "json",
    "tsconfig.json":   "json",
    "pyproject.toml":  "toml",
    "Cargo.toml":      "toml",
    "go.mod":          "go",
    "go.sum":          "text",
    "pom.xml":         "xml",
    "build.gradle":    "groovy",
    "build.gradle.kts": "kotlin",
    "CMakeLists.txt":  "cmake",
    "MANIFEST.in":     "text",
    "setup.cfg":       "ini",
    "tox.ini":         "ini",
    ".eslintrc":       "json",
    ".babelrc":        "json",
    ".prettierrc":     "json",
}


# =============================================================================
# Shebang Detector
# =============================================================================

class ShebangDetector:
    """
    Detects language from the shebang line at the top of a file.

    Shebangs like #!/usr/bin/env python3 reliably indicate the language
    even for extensionless scripts.
    """

    SHEBANG_MAP: dict[str, str] = {
        "python":     "python",
        "python3":    "python",
        "python2":    "python",
        "node":       "javascript",
        "nodejs":     "javascript",
        "deno":       "typescript",
        "ruby":       "ruby",
        "perl":       "perl",
        "php":        "php",
        "bash":       "bash",
        "sh":         "bash",
        "zsh":        "bash",
        "fish":       "bash",
        "lua":        "lua",
        "rscript":    "r",
        "Rscript":    "r",
        "groovy":     "groovy",
        "kotlin":     "kotlin",
        "swift":      "swift",
    }

    @classmethod
    def detect(cls, first_line: str) -> str | None:
        """
        Detect language from a shebang line.

        Args:
            first_line: First line of the file content

        Returns:
            Language ID string or None if not a shebang
        """
        if not first_line.startswith("#!"):
            return None

        shebang = first_line[2:].strip()

        # Handle /usr/bin/env INTERPRETER
        env_match = re.search(r"/env\s+(\S+)", shebang)
        if env_match:
            interpreter = env_match.group(1).split("/")[-1].lower()
            # Strip version suffix: python3.11 -> python3 -> python
            base = re.sub(r"[\d.]+$", "", interpreter)
            return cls.SHEBANG_MAP.get(base) or cls.SHEBANG_MAP.get(interpreter)

        # Handle direct path: /usr/bin/python
        path_match = re.search(r"/([^/\s]+)\s*$", shebang)
        if path_match:
            interpreter = path_match.group(1).lower()
            base = re.sub(r"[\d.]+$", "", interpreter)
            return cls.SHEBANG_MAP.get(base) or cls.SHEBANG_MAP.get(interpreter)

        return None


# =============================================================================
# Content Heuristics Detector
# =============================================================================

class ContentHeuristicsDetector:
    """
    Detects language from content patterns when extension is ambiguous.

    Uses weighted scoring: each matched pattern adds score points.
    The language with the highest score wins.
    """

    # Patterns: list of (regex, weight, language_id)
    PATTERNS: list[tuple[re.Pattern, int, str]] = [
        # Python
        (re.compile(r"^import\s+\w|^from\s+\w+\s+import", re.M), 3, "python"),
        (re.compile(r"^def\s+\w+\s*\(|^async\s+def\s+\w+", re.M), 4, "python"),
        (re.compile(r"^class\s+\w+.*:$", re.M), 2, "python"),
        (re.compile(r'""".*?"""', re.DOTALL), 2, "python"),
        (re.compile(r"print\(|__name__\s*==\s*[\"']__main__[\"']"), 2, "python"),
        (re.compile(r":\s*$", re.M), 1, "python"),  # colon at end of line

        # JavaScript
        (re.compile(r"const\s+\w+\s*=|let\s+\w+\s*=|var\s+\w+\s*="), 2, "javascript"),
        (re.compile(r"function\s+\w+\s*\(|=>\s*\{"), 3, "javascript"),
        (re.compile(r"require\s*\(|module\.exports"), 4, "javascript"),
        (re.compile(r"console\.(log|error|warn)\s*\("), 2, "javascript"),
        (re.compile(r"document\.|window\.|navigator\."), 3, "javascript"),
        (re.compile(r'import\s+\w+\s+from\s+["\']'), 2, "javascript"),

        # TypeScript
        (re.compile(r":\s*\w+(\[\])?\s*[=;,)\n]"), 3, "typescript"),
        (re.compile(r"interface\s+\w+\s*\{|type\s+\w+\s*="), 4, "typescript"),
        (re.compile(r"<\w+>|Array<|Promise<|Optional<"), 3, "typescript"),
        (re.compile(r":\s*(?:string|number|boolean|void|any)\b"), 4, "typescript"),
        (re.compile(r"as\s+\w+|as\s+unknown"), 2, "typescript"),

        # Java
        (re.compile(r"public\s+class\s+\w+|private\s+\w+\s+\w+;"), 5, "java"),
        (re.compile(r"@Override|@Autowired|@Service|@Component"), 4, "java"),
        (re.compile(r"System\.out\.println|throws\s+\w+"), 3, "java"),
        (re.compile(r"import\s+java\.|import\s+org\.spring"), 5, "java"),
        (re.compile(r"public\s+static\s+void\s+main"), 5, "java"),

        # Go
        (re.compile(r"^package\s+\w+", re.M), 5, "go"),
        (re.compile(r"^func\s+\w+\s*\(", re.M), 4, "go"),
        (re.compile(r":=\s*|fmt\.Print|log\.Fatal"), 3, "go"),
        (re.compile(r"make\(|chan\s+\w+|go\s+func"), 4, "go"),
        (re.compile(r'import\s+\(\s*"fmt"'), 4, "go"),

        # Rust
        (re.compile(r"^fn\s+\w+|^pub\s+fn", re.M), 4, "rust"),
        (re.compile(r"let\s+mut\s+\w+|impl\s+\w+"), 4, "rust"),
        (re.compile(r"use\s+std::|use\s+\w+::\{"), 4, "rust"),
        (re.compile(r"Option<|Result<|Vec<|HashMap<"), 3, "rust"),
        (re.compile(r"#\[derive\(|#\[cfg\("), 5, "rust"),

        # C++
        (re.compile(r"#include\s+<\w+>|#include\s+\"\w+"), 4, "cpp"),
        (re.compile(r"std::|cout\s*<<|cin\s*>>"), 3, "cpp"),
        (re.compile(r"template\s*<|namespace\s+\w+"), 4, "cpp"),
        (re.compile(r"nullptr|auto\s+\w+\s*="), 3, "cpp"),

        # SQL
        (re.compile(r"SELECT\s+\w|INSERT\s+INTO|UPDATE\s+\w+\s+SET",
                    re.IGNORECASE), 5, "sql"),
        (re.compile(r"CREATE\s+TABLE|DROP\s+TABLE|ALTER\s+TABLE",
                    re.IGNORECASE), 5, "sql"),
        (re.compile(r"WHERE\s+\w+\s*=|JOIN\s+\w+|GROUP\s+BY",
                    re.IGNORECASE), 3, "sql"),

        # Ruby
        (re.compile(r"^require\s+[\"']\w|^gem\s+[\"']", re.M), 4, "ruby"),
        (re.compile(r"def\s+\w+.*\nend\b", re.DOTALL), 4, "ruby"),
        (re.compile(r"\.each\s*do\s*\||\.map\s*{"), 3, "ruby"),
        (re.compile(r"puts\s+|attr_accessor|Rails\.|ActiveRecord"),
         4, "ruby"),
    ]

    @classmethod
    def detect(cls, content: str, top_n: int = 1) -> list[tuple[str, int]]:
        """
        Score content against all language patterns.

        Args:
            content:   File content string (first 3000 chars is enough)
            top_n:     Number of top candidates to return

        Returns:
            List of (language_id, score) tuples sorted by score desc
        """
        sample = content[:3000]
        scores: dict[str, int] = {}

        for pattern, weight, lang_id in cls.PATTERNS:
            matches = len(pattern.findall(sample))
            if matches:
                scores[lang_id] = scores.get(lang_id, 0) + weight * min(matches, 3)

        if not scores:
            return [("unknown", 0)]

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_n]


# =============================================================================
# Main Language Detector
# =============================================================================

class LanguageDetector:
    """
    Main language detection engine combining all detection strategies.

    Detection priority:
        1. Filename match (Makefile, Dockerfile, etc.)
        2. File extension lookup (fastest, most reliable)
        3. Shebang line detection (#!)
        4. Content heuristics (fallback for ambiguous cases)
        5. "unknown" if nothing matches

    Returns both the detected language ID and a confidence score.
    """

    @classmethod
    def detect(
        cls,
        file_path: str,
        content: str = "",
    ) -> dict[str, Any]:
        """
        Detect the language of a file using all available strategies.

        Args:
            file_path: File path (used for extension and filename lookup)
            content:   File content (used for shebang and heuristics)

        Returns:
            Dict with keys:
                language_id  (str)  e.g. "python"
                confidence   (str)  "high" | "medium" | "low"
                method       (str)  detection method used
                info         (dict | None) LanguageInfo.to_dict() if known
        """
        path = Path(file_path)
        filename = path.name
        ext = path.suffix.lower()

        # ── Strategy 1: Exact filename match ──────────────────────
        if filename in FILENAME_MAP:
            lang_id = FILENAME_MAP[filename]
            return {
                "language_id": lang_id,
                "confidence": "high",
                "method": "filename",
                "info": LANGUAGES.get(lang_id, {}) and
                        LANGUAGES[lang_id].to_dict() if lang_id in LANGUAGES else None,
            }

        # ── Strategy 2: Extension lookup ──────────────────────────
        if ext and ext in EXTENSION_MAP:
            lang_id = EXTENSION_MAP[ext]
            return {
                "language_id": lang_id,
                "confidence": "high",
                "method": "extension",
                "info": LANGUAGES[lang_id].to_dict()
                        if lang_id in LANGUAGES else None,
            }

        # ── Strategy 3: Shebang line ───────────────────────────────
        if content:
            first_line = content.splitlines()[0] if content else ""
            shebang_lang = ShebangDetector.detect(first_line)
            if shebang_lang:
                return {
                    "language_id": shebang_lang,
                    "confidence": "high",
                    "method": "shebang",
                    "info": LANGUAGES[shebang_lang].to_dict()
                            if shebang_lang in LANGUAGES else None,
                }

            # ── Strategy 4: Content heuristics ────────────────────
            if len(content.strip()) > 50:
                top = ContentHeuristicsDetector.detect(content, top_n=2)
                if top and top[0][1] >= 4:
                    lang_id, score = top[0]
                    confidence = "high" if score >= 10 else "medium"
                    return {
                        "language_id": lang_id,
                        "confidence": confidence,
                        "method": "heuristics",
                        "score": score,
                        "info": LANGUAGES[lang_id].to_dict()
                                if lang_id in LANGUAGES else None,
                    }
                elif top and top[0][1] >= 2:
                    lang_id, score = top[0]
                    return {
                        "language_id": lang_id,
                        "confidence": "low",
                        "method": "heuristics",
                        "score": score,
                        "info": LANGUAGES[lang_id].to_dict()
                                if lang_id in LANGUAGES else None,
                    }

        # ── Strategy 5: Unknown ────────────────────────────────────
        return {
            "language_id": "unknown",
            "confidence": "none",
            "method": "none",
            "info": None,
        }

    @classmethod
    def detect_batch(
        cls,
        files: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """
        Detect language for a batch of files.

        Args:
            files: List of {"path": str, "content": str} dicts

        Returns:
            List of detection result dicts (one per file)
        """
        results: list[dict[str, Any]] = []
        for f in files:
            path = str(f.get("path") or "")
            content = str(f.get("content") or "")
            result = cls.detect(path, content)
            result["file_path"] = path
            results.append(result)
        return results

    @classmethod
    def get_project_language_stats(
        cls,
        files: list[dict[str, str]],
    ) -> dict[str, Any]:
        """
        Analyze a project's language composition.

        Args:
            files: List of {"path": str, "content": str} dicts

        Returns:
            Dict with language breakdown, primary language, stats
        """
        from collections import Counter

        detections = cls.detect_batch(files)

        lang_counter: Counter = Counter()
        lang_bytes: dict[str, int] = {}
        lang_files: dict[str, list[str]] = {}

        for det, f in zip(detections, files):
            lang_id = det["language_id"]
            path = str(f.get("path") or "")
            content = str(f.get("content") or "")

            lang_counter[lang_id] += 1
            lang_bytes[lang_id] = (
                lang_bytes.get(lang_id, 0) + len(content.encode("utf-8"))
            )
            if lang_id not in lang_files:
                lang_files[lang_id] = []
            if len(lang_files[lang_id]) < 5:
                lang_files[lang_id].append(path)

        total_files = len(files)
        total_bytes = sum(lang_bytes.values())

        # Build breakdown sorted by file count
        breakdown: list[dict[str, Any]] = []
        for lang_id, count in lang_counter.most_common():
            info = LANGUAGES.get(lang_id)
            breakdown.append({
                "language_id": lang_id,
                "display_name": info.display_name if info else lang_id.title(),
                "file_count": count,
                "file_percentage": round(count / max(total_files, 1) * 100, 1),
                "bytes": lang_bytes.get(lang_id, 0),
                "byte_percentage": round(
                    lang_bytes.get(lang_id, 0) / max(total_bytes, 1) * 100, 1
                ),
                "color": info.color if info else "#888888",
                "sample_files": lang_files.get(lang_id, [])[:3],
            })

        # Primary language (most files, excluding config/markup)
        code_langs = [
            b for b in breakdown
            if b["language_id"] not in (
                "unknown", "json", "yaml", "toml", "ini",
                "markdown", "text", "gitignore", "env",
            )
        ]
        primary = code_langs[0]["language_id"] if code_langs else (
            breakdown[0]["language_id"] if breakdown else "unknown"
        )

        return {
            "primary_language": primary,
            "total_files": total_files,
            "total_bytes": total_bytes,
            "language_count": len(lang_counter),
            "breakdown": breakdown,
            "is_polyglot": len(code_langs) > 1,
        }


# =============================================================================
# Language Router
# =============================================================================

class LanguageRouter:
    """
    Routes files to the correct processing pipeline based on language.

    Provides concrete recommendations for:
    - Which parser to use (AST vs regex vs generic)
    - Which agent system prompt to use
    - Which chunking strategy to apply
    - Which complexity analyzer to use
    """

    # Routing rules: language_id -> processing recommendations
    ROUTING_TABLE: dict[str, dict[str, str]] = {
        "python": {
            "parser": "ast",
            "chunking": "by_function",
            "complexity": "cyclomatic+cognitive+halstead",
            "doc_format": "google_docstring",
            "test_format": "pytest",
            "security_scanner": "python",
            "prompt_template": "python",
        },
        "javascript": {
            "parser": "regex",
            "chunking": "by_function",
            "complexity": "approximate",
            "doc_format": "jsdoc",
            "test_format": "jest",
            "security_scanner": "javascript",
            "prompt_template": "javascript",
        },
        "typescript": {
            "parser": "regex",
            "chunking": "by_function",
            "complexity": "approximate",
            "doc_format": "tsdoc",
            "test_format": "jest",
            "security_scanner": "javascript",
            "prompt_template": "typescript",
        },
        "java": {
            "parser": "regex",
            "chunking": "by_class",
            "complexity": "approximate",
            "doc_format": "javadoc",
            "test_format": "junit",
            "security_scanner": "generic",
            "prompt_template": "java",
        },
        "go": {
            "parser": "regex",
            "chunking": "by_function",
            "complexity": "approximate",
            "doc_format": "godoc",
            "test_format": "go_test",
            "security_scanner": "generic",
            "prompt_template": "go",
        },
        "rust": {
            "parser": "regex",
            "chunking": "by_function",
            "complexity": "approximate",
            "doc_format": "rustdoc",
            "test_format": "cargo_test",
            "security_scanner": "generic",
            "prompt_template": "rust",
        },
    }

    DEFAULT_ROUTE: dict[str, str] = {
        "parser": "generic",
        "chunking": "by_lines",
        "complexity": "loc_only",
        "doc_format": "comment_block",
        "test_format": "generic",
        "security_scanner": "generic",
        "prompt_template": "generic",
    }

    @classmethod
    def route(cls, language_id: str) -> dict[str, str]:
        """
        Get processing route for a language.

        Args:
            language_id: Detected language ID

        Returns:
            Routing dict with parser, chunking, etc. recommendations
        """
        return cls.ROUTING_TABLE.get(language_id, cls.DEFAULT_ROUTE).copy()

    @classmethod
    def get_system_prompt_context(cls, language_id: str) -> dict[str, str]:
        """
        Get language-specific context for LLM system prompts.

        Returns comment syntax, naming conventions, and idioms
        to inject into agent system prompts for better accuracy.

        Args:
            language_id: Detected language ID

        Returns:
            Dict with prompt context strings
        """
        info = LANGUAGES.get(language_id)
        if not info:
            return {
                "language": language_id,
                "comment_style": "#",
                "doc_style": "comment blocks",
                "naming": "snake_case for variables",
                "conventions": "Follow the language style guide",
            }

        # Language-specific conventions
        naming_map = {
            "python":     "snake_case functions/vars, PascalCase classes",
            "javascript": "camelCase functions/vars, PascalCase classes",
            "typescript": "camelCase functions/vars, PascalCase classes/interfaces",
            "java":       "camelCase methods/vars, PascalCase classes",
            "go":         "camelCase unexported, PascalCase exported",
            "rust":       "snake_case functions/vars, PascalCase types",
            "cpp":        "snake_case or camelCase (project-dependent)",
            "csharp":     "PascalCase methods/classes, camelCase vars",
            "ruby":       "snake_case methods/vars, PascalCase classes",
        }

        return {
            "language": info.display_name,
            "comment_single": info.comment_single,
            "comment_multi": f"{info.comment_multi_start} ... {info.comment_multi_end}",
            "doc_style": info.doc_style,
            "naming_conventions": naming_map.get(language_id, "follow language style"),
            "test_framework": info.test_frameworks[0] if info.test_frameworks else "N/A",
            "typing": info.typing,
            "popular_frameworks": ", ".join(info.popular_frameworks[:3]),
        }
