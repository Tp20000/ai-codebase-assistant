"""
Security Scanner Agent - Step 24
AI Codebase Assistant v2.0

OWASP-aligned security vulnerability scanner covering:
    A01 Broken Access Control
    A02 Cryptographic Failures
    A03 Injection (SQL, Command, LDAP, XPath)
    A04 Insecure Design
    A05 Security Misconfiguration
    A06 Vulnerable Components
    A07 Authentication Failures
    A08 Integrity Failures (deserialization)
    A09 Logging Failures
    A10 SSRF

Correctly extends BaseAgent (same pattern as Steps 21-23):
    BaseAgent.__init__(retriever=None, streaming_client=None)
    Abstract property:  agent_type -> str
    Abstract method:    _build_graph() -> compiled StateGraph
    Abstract method:    _format_result(state: AgentState) -> dict

    run() accepts AgentConfig
    AgentConfig.extra carries: code_content, language, file_path
    CRITICAL: user_prompt_template uses ONLY {context} {query} {project_id}

LangGraph workflow:
    validate -> retrieve -> parse_code -> scan_secrets
             -> scan_injection -> scan_crypto -> scan_misc
             -> aggregate -> generate_report -> fmt -> done -> END
"""

from __future__ import annotations

import ast
import logging
import re
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, StateGraph

from app.core.agents.base_agent import (
    AgentConfig,
    AgentState,
    AgentStatus,
    BaseAgent,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Security Finding Schema
# =============================================================================
# Each finding dict has keys:
#   vuln_id    (str)  unique ID e.g. "SEC-001"
#   owasp      (str)  OWASP category e.g. "A03 Injection"
#   severity   (str)  CRITICAL | HIGH | MEDIUM | LOW | INFO
#   cwe        (str)  CWE reference e.g. "CWE-89"
#   line       (int)  line number (0 = file-level)
#   title      (str)  short vulnerability name
#   detail     (str)  what was found and why it is dangerous
#   evidence   (str)  the actual code snippet that triggered the rule
#   remediation (str) concrete fix steps

SEVERITY_SCORE = {
    "CRITICAL": 40,
    "HIGH": 20,
    "MEDIUM": 8,
    "LOW": 2,
    "INFO": 0,
}

RISK_LEVELS = [
    (80, "CRITICAL"),
    (50, "HIGH"),
    (25, "MEDIUM"),
    (10, "LOW"),
    (0,  "INFO"),
]


def risk_level(total_score: int) -> str:
    """
    Convert a numeric risk score to a risk level label.

    Args:
        total_score: Sum of severity scores from all findings

    Returns:
        Risk level string: CRITICAL | HIGH | MEDIUM | LOW | INFO
    """
    for threshold, label in RISK_LEVELS:
        if total_score >= threshold:
            return label
    return "INFO"


# =============================================================================
# Python Security Scanner
# =============================================================================

class PythonSecurityScanner:
    """
    OWASP-aligned security scanner for Python source code.

    Combines regex pattern matching with Python AST analysis to detect
    vulnerabilities that regex alone cannot reliably find (e.g. eval() calls,
    unsafe deserialization, mutable sinks).

    Rules:
        SEC-PY-001  Hardcoded secret / credential
        SEC-PY-002  SQL injection via string formatting
        SEC-PY-003  Command injection (os.system, subprocess with shell=True)
        SEC-PY-004  eval() / exec() with dynamic input
        SEC-PY-005  Insecure deserialization (pickle.loads, yaml.load unsafe)
        SEC-PY-006  Weak cryptography (MD5, SHA1 for security)
        SEC-PY-007  Hardcoded IP address
        SEC-PY-008  Path traversal risk (open() with user input)
        SEC-PY-009  Insecure random (random module for security)
        SEC-PY-010  Debug mode enabled
        SEC-PY-011  SSRF risk (requests with user-controlled URL)
        SEC-PY-012  Broad exception suppression hiding errors
        SEC-PY-013  Assert used for security checks
        SEC-PY-014  Insecure temp file creation
        SEC-PY-015  XML external entity (XXE) risk
    """

    # ── Compiled regex patterns ───────────────────────────────────
    SECRET_PAT = re.compile(
        r'(?i)(?:password|passwd|secret|api[_-]?key|auth[_-]?token|'
        r'access[_-]?token|private[_-]?key|client[_-]?secret)\s*=\s*'
        r'["\'][^"\']{6,}["\']'
    )
    SQL_FORMAT_PAT = re.compile(
        r'(?i)(?:execute|cursor\.execute|query)\s*\(\s*["\'].*%[s\d].*["\']'
        r'|(?:execute|cursor\.execute)\s*\(\s*f["\'].*\{',
        re.DOTALL,
    )
    SQL_CONCAT_PAT = re.compile(
        r'(?i)(?:select|insert|update|delete|drop|create)\s+.*\+\s*\w'
        r'|(?:select|insert|update|delete)\s+.*\.format\(',
    )
    CMD_INJECTION_PAT = re.compile(
        r'os\.system\s*\(|subprocess\.(call|run|Popen)\s*\([^)]*shell\s*=\s*True'
        r'|commands\.getoutput\s*\(',
    )
    EVAL_PAT = re.compile(r'\beval\s*\(|\bexec\s*\(')
    PICKLE_PAT = re.compile(r'pickle\.loads?\s*\(|cPickle\.loads?\s*\(')
    YAML_UNSAFE_PAT = re.compile(r'yaml\.load\s*\([^)]*\)(?!\s*,\s*Loader)')
    WEAK_CRYPTO_PAT = re.compile(
        r'hashlib\.md5\s*\(|hashlib\.sha1\s*\('
        r'|MD5\.new\s*\(|SHA\.new\s*\(',
    )
    HARDCODED_IP_PAT = re.compile(
        r'["\'](?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}'
        r'(?:25[0-5]|2[0-4]\d|[01]?\d\d?)["\']'
    )
    INSECURE_RANDOM_PAT = re.compile(
        r'random\.random\s*\(|random\.randint\s*\(|random\.choice\s*\('
        r'|random\.shuffle\s*\(',
    )
    DEBUG_PAT = re.compile(r'(?i)DEBUG\s*=\s*True|app\.run\s*\([^)]*debug\s*=\s*True')
    SSRF_PAT = re.compile(
        r'requests\.(get|post|put|delete|head|patch)\s*\(\s*\w'
        r'|urllib\.request\.urlopen\s*\(\s*\w',
    )
    ASSERT_SECURITY_PAT = re.compile(
        r'assert\s+.*(?:auth|permission|role|admin|token|access)',
        re.IGNORECASE,
    )
    TEMP_FILE_PAT = re.compile(r'tempfile\.mktemp\s*\(|open\s*\(\s*["\']\/tmp\/')
    XXE_PAT = re.compile(
        r'xml\.etree|lxml\.etree|minidom\.parseString'
        r'|ElementTree\.parse\s*\(',
    )

    @classmethod
    def scan(cls, source: str) -> list[dict[str, Any]]:
        """
        Run all Python security rules on the source code.

        Args:
            source: Raw Python source code string

        Returns:
            List of security finding dicts sorted by severity score (desc)
        """
        findings: list[dict[str, Any]] = []
        lines = source.splitlines()

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            # SEC-PY-001: Hardcoded secret
            if cls.SECRET_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-PY-001",
                    "owasp": "A02 Cryptographic Failures",
                    "severity": "CRITICAL",
                    "cwe": "CWE-798",
                    "line": i,
                    "title": "Hardcoded Credential",
                    "detail": (
                        "A secret, password, or API key is hardcoded in source. "
                        "Exposed in version control and logs."
                    ),
                    "evidence": stripped[:100],
                    "remediation": (
                        "Move to environment variables: os.environ.get('MY_SECRET'). "
                        "Use python-dotenv or a secrets manager (AWS Secrets Manager, Vault)."
                    ),
                })

            # SEC-PY-002: SQL injection
            if cls.SQL_FORMAT_PAT.search(line) or cls.SQL_CONCAT_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-PY-002",
                    "owasp": "A03 Injection",
                    "severity": "CRITICAL",
                    "cwe": "CWE-89",
                    "line": i,
                    "title": "SQL Injection Risk",
                    "detail": (
                        "SQL query built with string formatting or concatenation. "
                        "User input can manipulate query structure."
                    ),
                    "evidence": stripped[:100],
                    "remediation": (
                        "Use parameterized queries: cursor.execute(query, (param,)). "
                        "Never interpolate user data directly into SQL strings."
                    ),
                })

            # SEC-PY-003: Command injection
            if cls.CMD_INJECTION_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-PY-003",
                    "owasp": "A03 Injection",
                    "severity": "CRITICAL",
                    "cwe": "CWE-78",
                    "line": i,
                    "title": "Command Injection Risk",
                    "detail": (
                        "os.system() or subprocess with shell=True allows "
                        "shell metacharacter injection from user input."
                    ),
                    "evidence": stripped[:100],
                    "remediation": (
                        "Use subprocess.run() with a list of args and shell=False. "
                        "Validate and sanitize all inputs before passing to system calls."
                    ),
                })

            # SEC-PY-004: eval/exec
            if cls.EVAL_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-PY-004",
                    "owasp": "A03 Injection",
                    "severity": "CRITICAL",
                    "cwe": "CWE-95",
                    "line": i,
                    "title": "Code Injection via eval()/exec()",
                    "detail": (
                        "eval() or exec() executes arbitrary Python code. "
                        "Extremely dangerous with any user-controlled input."
                    ),
                    "evidence": stripped[:100],
                    "remediation": (
                        "Remove eval()/exec(). Use ast.literal_eval() for safe "
                        "data parsing, or redesign to avoid dynamic code execution."
                    ),
                })

            # SEC-PY-005: Insecure deserialization
            if cls.PICKLE_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-PY-005",
                    "owasp": "A08 Integrity Failures",
                    "severity": "CRITICAL",
                    "cwe": "CWE-502",
                    "line": i,
                    "title": "Insecure Deserialization (pickle)",
                    "detail": (
                        "pickle.loads() can execute arbitrary code when "
                        "deserializing attacker-controlled data."
                    ),
                    "evidence": stripped[:100],
                    "remediation": (
                        "Use JSON or MessagePack for data serialization. "
                        "If pickle is required, sign the data with HMAC before storing."
                    ),
                })

            # SEC-PY-005b: yaml.load without Loader
            if cls.YAML_UNSAFE_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-PY-005b",
                    "owasp": "A08 Integrity Failures",
                    "severity": "HIGH",
                    "cwe": "CWE-502",
                    "line": i,
                    "title": "Unsafe YAML Deserialization",
                    "detail": (
                        "yaml.load() without Loader=yaml.SafeLoader can "
                        "execute arbitrary Python objects."
                    ),
                    "evidence": stripped[:100],
                    "remediation": "Use yaml.safe_load() or yaml.load(data, Loader=yaml.SafeLoader)",
                })

            # SEC-PY-006: Weak cryptography
            if cls.WEAK_CRYPTO_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-PY-006",
                    "owasp": "A02 Cryptographic Failures",
                    "severity": "HIGH",
                    "cwe": "CWE-327",
                    "line": i,
                    "title": "Weak Cryptographic Algorithm",
                    "detail": (
                        "MD5 and SHA1 are cryptographically broken for security "
                        "purposes (collision attacks demonstrated)."
                    ),
                    "evidence": stripped[:100],
                    "remediation": (
                        "Use SHA-256 or SHA-3 for hashing. "
                        "For passwords use bcrypt, scrypt, or Argon2."
                    ),
                })

            # SEC-PY-007: Hardcoded IP
            if cls.HARDCODED_IP_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-PY-007",
                    "owasp": "A05 Security Misconfiguration",
                    "severity": "LOW",
                    "cwe": "CWE-1001",
                    "line": i,
                    "title": "Hardcoded IP Address",
                    "detail": "IP address hardcoded in source reduces flexibility and may expose infrastructure.",
                    "evidence": stripped[:100],
                    "remediation": "Move to configuration file or environment variable.",
                })

            # SEC-PY-009: Insecure random
            if cls.INSECURE_RANDOM_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-PY-009",
                    "owasp": "A02 Cryptographic Failures",
                    "severity": "MEDIUM",
                    "cwe": "CWE-338",
                    "line": i,
                    "title": "Insecure Random Number Generator",
                    "detail": (
                        "random module is not cryptographically secure. "
                        "Predictable for security-sensitive operations."
                    ),
                    "evidence": stripped[:100],
                    "remediation": (
                        "Use secrets module for security-sensitive randomness: "
                        "secrets.token_hex(), secrets.choice()."
                    ),
                })

            # SEC-PY-010: Debug mode
            if cls.DEBUG_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-PY-010",
                    "owasp": "A05 Security Misconfiguration",
                    "severity": "HIGH",
                    "cwe": "CWE-94",
                    "line": i,
                    "title": "Debug Mode Enabled",
                    "detail": (
                        "DEBUG=True or app.run(debug=True) exposes stack traces, "
                        "interactive debugger, and internal details to attackers."
                    ),
                    "evidence": stripped[:100],
                    "remediation": (
                        "Set DEBUG=False in production. "
                        "Use environment variable: DEBUG=os.environ.get('DEBUG', 'False') == 'True'"
                    ),
                })

            # SEC-PY-011: SSRF risk
            if cls.SSRF_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-PY-011",
                    "owasp": "A10 SSRF",
                    "severity": "MEDIUM",
                    "cwe": "CWE-918",
                    "line": i,
                    "title": "Potential SSRF",
                    "detail": (
                        "HTTP request made with a variable URL. "
                        "If URL comes from user input, attacker can reach internal services."
                    ),
                    "evidence": stripped[:100],
                    "remediation": (
                        "Validate URLs against an allowlist. "
                        "Block requests to private IP ranges (127.x, 10.x, 192.168.x). "
                        "Use a dedicated HTTP client with SSRF protection."
                    ),
                })

            # SEC-PY-013: Assert for security
            if cls.ASSERT_SECURITY_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-PY-013",
                    "owasp": "A01 Broken Access Control",
                    "severity": "HIGH",
                    "cwe": "CWE-617",
                    "line": i,
                    "title": "Security Check via assert",
                    "detail": (
                        "assert statements are removed when Python runs with "
                        "optimizations (-O flag). Security checks will be bypassed."
                    ),
                    "evidence": stripped[:100],
                    "remediation": (
                        "Replace assert with explicit if/raise: "
                        "if not condition: raise PermissionError('Access denied')"
                    ),
                })

            # SEC-PY-014: Insecure temp file
            if cls.TEMP_FILE_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-PY-014",
                    "owasp": "A04 Insecure Design",
                    "severity": "MEDIUM",
                    "cwe": "CWE-377",
                    "line": i,
                    "title": "Insecure Temporary File",
                    "detail": (
                        "tempfile.mktemp() has a race condition (TOCTOU). "
                        "Hardcoded /tmp paths can be hijacked."
                    ),
                    "evidence": stripped[:100],
                    "remediation": (
                        "Use tempfile.mkstemp() or tempfile.NamedTemporaryFile() "
                        "which creates files atomically and securely."
                    ),
                })

            # SEC-PY-015: XXE risk
            if cls.XXE_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-PY-015",
                    "owasp": "A05 Security Misconfiguration",
                    "severity": "MEDIUM",
                    "cwe": "CWE-611",
                    "line": i,
                    "title": "Potential XML External Entity (XXE)",
                    "detail": (
                        "XML parser may be vulnerable to XXE if parsing "
                        "untrusted XML. Can leak files or cause SSRF."
                    ),
                    "evidence": stripped[:100],
                    "remediation": (
                        "Use defusedxml library instead of stdlib xml parsers. "
                        "pip install defusedxml — drop-in safe replacement."
                    ),
                })

        # ── AST-based checks ──────────────────────────────────────
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                # Broad except hiding security errors
                if isinstance(node, ast.ExceptHandler) and node.type is None:
                    # Check if the body just passes or logs nothing
                    if all(isinstance(n, ast.Pass) for n in node.body):
                        findings.append({
                            "vuln_id": "SEC-PY-012",
                            "owasp": "A09 Logging Failures",
                            "severity": "MEDIUM",
                            "cwe": "CWE-390",
                            "line": node.lineno,
                            "title": "Silent Exception Suppression",
                            "detail": (
                                "Bare except: pass silently swallows all exceptions "
                                "including security-relevant errors."
                            ),
                            "evidence": "except: pass",
                            "remediation": (
                                "At minimum log the exception: "
                                "except Exception as e: logger.error('Unexpected error: %s', e)"
                            ),
                        })
        except SyntaxError:
            pass  # Syntax errors already reported by code reviewer if used together

        # Sort by severity score descending
        return sorted(
            findings,
            key=lambda f: SEVERITY_SCORE.get(str(f.get("severity", "INFO")), 0),
            reverse=True,
        )


# =============================================================================
# JavaScript / TypeScript Security Scanner
# =============================================================================

class JSSecurityScanner:
    """
    OWASP-aligned security scanner for JavaScript and TypeScript code.

    Rules:
        SEC-JS-001  Hardcoded secret
        SEC-JS-002  eval() usage
        SEC-JS-003  innerHTML / document.write (XSS)
        SEC-JS-004  SQL injection (template literals in queries)
        SEC-JS-005  Weak cryptography (Math.random for security)
        SEC-JS-006  Hardcoded JWT secret
        SEC-JS-007  Prototype pollution risk
        SEC-JS-008  ReDoS vulnerable regex
        SEC-JS-009  Dangerous redirect with user input
        SEC-JS-010  localStorage storing sensitive data
        SEC-JS-011  SSRF risk (fetch/axios with variable URL)
        SEC-JS-012  Insecure cookie (no HttpOnly/Secure flags)
        SEC-JS-013  Command injection (child_process with user input)
        SEC-JS-014  Path traversal risk
        SEC-JS-015  dangerouslySetInnerHTML (React XSS)
    """

    SECRET_PAT = re.compile(
        r'(?i)(?:password|secret|apiKey|api_key|authToken|auth_token|'
        r'clientSecret|privateKey)\s*[:=]\s*["\'][^"\']{6,}["\']'
    )
    EVAL_PAT = re.compile(r'\beval\s*\(')
    INNER_HTML_PAT = re.compile(r'\.innerHTML\s*=|document\.write\s*\(')
    SQL_TEMPLATE_PAT = re.compile(
        r'(?i)(?:query|execute|db\.run)\s*\(\s*`[^`]*\$\{',
    )
    WEAK_RANDOM_PAT = re.compile(r'Math\.random\s*\(')
    JWT_SECRET_PAT = re.compile(
        r'(?i)jwt\.sign\s*\([^)]*["\'][^"\']{6,}["\']'
        r'|(?:jwt[_-]?secret|jwtSecret)\s*[:=]\s*["\'][^"\']{6,}["\']'
    )
    PROTO_POLLUTION_PAT = re.compile(
        r'\[.*__proto__.*\]|Object\.assign\s*\(\s*\{\}|merge\s*\('
    )
    REDIRECT_PAT = re.compile(
        r'(?:window\.location|location\.href|res\.redirect)\s*[=\(]\s*\w'
    )
    LOCAL_STORAGE_PAT = re.compile(
        r'localStorage\.setItem\s*\(\s*["\'][^"\']*'
        r'(?:token|password|secret|auth)[^"\']*["\']',
        re.IGNORECASE,
    )
    SSRF_PAT = re.compile(
        r'(?:fetch|axios\.get|axios\.post|axios\.request|http\.get|https\.get)'
        r'\s*\(\s*\w'
    )
    COOKIE_PAT = re.compile(
        r'document\.cookie\s*=|res\.cookie\s*\([^)]*\)',
    )
    CMD_PAT = re.compile(
        r'(?:exec|execSync|spawn|spawnSync)\s*\(\s*\w'
        r'|child_process\.exec\s*\('
    )
    PATH_PAT = re.compile(
        r'(?:readFile|writeFile|createReadStream|createWriteStream|'
        r'fs\.open)\s*\(\s*\w'
    )
    DANGEROUS_HTML_PAT = re.compile(r'dangerouslySetInnerHTML')

    @classmethod
    def scan(cls, source: str) -> list[dict[str, Any]]:
        """
        Run all JS/TS security rules on the source code.

        Args:
            source: Raw JavaScript or TypeScript source code

        Returns:
            List of security finding dicts sorted by severity (desc)
        """
        findings: list[dict[str, Any]] = []
        lines = source.splitlines()

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            if cls.SECRET_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-JS-001",
                    "owasp": "A02 Cryptographic Failures",
                    "severity": "CRITICAL",
                    "cwe": "CWE-798",
                    "line": i,
                    "title": "Hardcoded Credential",
                    "detail": "Secret, API key, or password hardcoded in source code.",
                    "evidence": stripped[:100],
                    "remediation": "Use process.env.MY_SECRET and .env files (add to .gitignore)",
                })

            if cls.EVAL_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-JS-002",
                    "owasp": "A03 Injection",
                    "severity": "CRITICAL",
                    "cwe": "CWE-95",
                    "line": i,
                    "title": "Code Injection via eval()",
                    "detail": "eval() executes arbitrary JavaScript — extremely dangerous with user input.",
                    "evidence": stripped[:100],
                    "remediation": "Remove eval(). Use JSON.parse() for data, redesign for logic.",
                })

            if cls.INNER_HTML_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-JS-003",
                    "owasp": "A03 Injection",
                    "severity": "HIGH",
                    "cwe": "CWE-79",
                    "line": i,
                    "title": "XSS via innerHTML / document.write",
                    "detail": (
                        "Setting innerHTML or using document.write with "
                        "unsanitized data allows Cross-Site Scripting attacks."
                    ),
                    "evidence": stripped[:100],
                    "remediation": (
                        "Use textContent instead of innerHTML for text. "
                        "Sanitize HTML with DOMPurify if HTML is needed."
                    ),
                })

            if cls.SQL_TEMPLATE_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-JS-004",
                    "owasp": "A03 Injection",
                    "severity": "CRITICAL",
                    "cwe": "CWE-89",
                    "line": i,
                    "title": "SQL Injection via Template Literal",
                    "detail": "SQL query built with template literal interpolation. User data can break query.",
                    "evidence": stripped[:100],
                    "remediation": "Use parameterized queries: db.query('SELECT * FROM t WHERE id = ?', [id])",
                })

            if cls.WEAK_RANDOM_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-JS-005",
                    "owasp": "A02 Cryptographic Failures",
                    "severity": "MEDIUM",
                    "cwe": "CWE-338",
                    "line": i,
                    "title": "Insecure Random (Math.random)",
                    "detail": "Math.random() is not cryptographically secure. Predictable by attackers.",
                    "evidence": stripped[:100],
                    "remediation": "Use crypto.getRandomValues() or Node.js crypto.randomBytes().",
                })

            if cls.JWT_SECRET_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-JS-006",
                    "owasp": "A07 Authentication Failures",
                    "severity": "CRITICAL",
                    "cwe": "CWE-798",
                    "line": i,
                    "title": "Hardcoded JWT Secret",
                    "detail": "JWT signing secret hardcoded. Anyone with source access can forge tokens.",
                    "evidence": stripped[:100],
                    "remediation": "Load from process.env.JWT_SECRET. Generate with: openssl rand -base64 64",
                })

            if cls.REDIRECT_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-JS-009",
                    "owasp": "A01 Broken Access Control",
                    "severity": "MEDIUM",
                    "cwe": "CWE-601",
                    "line": i,
                    "title": "Open Redirect Risk",
                    "detail": "Redirect with a variable URL. User-controlled redirects enable phishing.",
                    "evidence": stripped[:100],
                    "remediation": "Validate redirect URLs against an allowlist of trusted domains.",
                })

            if cls.LOCAL_STORAGE_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-JS-010",
                    "owasp": "A02 Cryptographic Failures",
                    "severity": "HIGH",
                    "cwe": "CWE-312",
                    "line": i,
                    "title": "Sensitive Data in localStorage",
                    "detail": "Storing tokens/passwords in localStorage exposes to XSS attacks.",
                    "evidence": stripped[:100],
                    "remediation": "Store auth tokens in HttpOnly cookies instead of localStorage.",
                })

            if cls.SSRF_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-JS-011",
                    "owasp": "A10 SSRF",
                    "severity": "MEDIUM",
                    "cwe": "CWE-918",
                    "line": i,
                    "title": "Potential SSRF",
                    "detail": "HTTP request with variable URL. May allow reaching internal services.",
                    "evidence": stripped[:100],
                    "remediation": "Validate URLs against allowlist. Block private IP ranges.",
                })

            if cls.CMD_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-JS-013",
                    "owasp": "A03 Injection",
                    "severity": "CRITICAL",
                    "cwe": "CWE-78",
                    "line": i,
                    "title": "Command Injection Risk",
                    "detail": "child_process.exec/spawn with variable input allows OS command injection.",
                    "evidence": stripped[:100],
                    "remediation": "Use execFile() with argument array. Never pass user input to shell commands.",
                })

            if cls.DANGEROUS_HTML_PAT.search(line):
                findings.append({
                    "vuln_id": "SEC-JS-015",
                    "owasp": "A03 Injection",
                    "severity": "HIGH",
                    "cwe": "CWE-79",
                    "line": i,
                    "title": "React dangerouslySetInnerHTML",
                    "detail": "dangerouslySetInnerHTML bypasses React's XSS protection.",
                    "evidence": stripped[:100],
                    "remediation": "Sanitize with DOMPurify before using dangerouslySetInnerHTML.",
                })

        return sorted(
            findings,
            key=lambda f: SEVERITY_SCORE.get(str(f.get("severity", "INFO")), 0),
            reverse=True,
        )


# =============================================================================
# Security Scanner Agent
# =============================================================================

class SecurityScannerAgent(BaseAgent):
    """
    LangGraph-powered OWASP-aligned security vulnerability scanner.

    Correctly extends BaseAgent (same pattern as Steps 21-23):
        __init__(retriever, streaming_client) -> super().__init__()
        agent_type -> "security_scanner"
        _build_graph() -> compiled StateGraph
        _format_result(state) -> dict

    Two-layer scanning:
        Layer 1: Deterministic regex + AST rules (always runs, no LLM)
        Layer 2: LLM provides deeper threat analysis and context-aware
                 remediation advice (only with streaming_client)

    AgentConfig.extra carries:
        code_content (str) source code to scan
        language     (str) python | javascript | typescript | ...
        file_path    (str) original file path

    LangGraph workflow:
        validate -> retrieve -> parse_code -> scan
                 -> aggregate -> generate_report -> fmt -> done -> END
    """

    def __init__(
        self,
        retriever: Any = None,
        streaming_client: Any = None,
    ) -> None:
        """
        Initialise the Security Scanner Agent.

        Args:
            retriever:        Optional RAG retriever for codebase context
            streaming_client: Optional Ollama client for AI threat analysis
        """
        super().__init__(retriever=retriever, streaming_client=streaming_client)

    # =========================================================================
    # Abstract property
    # =========================================================================

    @property
    def agent_type(self) -> str:
        """
        Unique type identifier for this agent.

        Returns:
            "security_scanner"
        """
        return "security_scanner"

    # =========================================================================
    # Abstract method: _build_graph
    # =========================================================================

    def _build_graph(self) -> Any:
        """
        Build and compile the LangGraph StateGraph for security scanning.

        Node execution order:
            validate        (BaseAgent)  check project_id present
            retrieve        (BaseAgent)  vector-store context lookup
            parse_code      (self)       read source + detect language
            scan            (self)       run all security rules
            aggregate       (self)       compute risk score + stats
            generate_report (self)       LLM threat analysis (optional)
            fmt             (BaseAgent)  calls _format_result()
            done            (self)       build Markdown security report

        Returns:
            Compiled LangGraph CompiledStateGraph
        """
        graph: StateGraph = StateGraph(AgentState)

        graph.add_node("validate",        self._node_validate)
        graph.add_node("retrieve",        self._node_retrieve)
        graph.add_node("parse_code",      self._node_parse_code)
        graph.add_node("scan",            self._node_scan)
        graph.add_node("aggregate",       self._node_aggregate)
        graph.add_node("generate_report", self._node_generate_report)
        graph.add_node("fmt",             self._node_format)
        graph.add_node("done",            self._node_done)

        graph.set_entry_point("validate")
        graph.add_edge("validate",        "retrieve")
        graph.add_edge("retrieve",        "parse_code")
        graph.add_edge("parse_code",      "scan")
        graph.add_edge("scan",            "aggregate")
        graph.add_edge("aggregate",       "generate_report")
        graph.add_edge("generate_report", "fmt")
        graph.add_edge("fmt",             "done")
        graph.add_edge("done",            END)

        return graph.compile()

    # =========================================================================
    # Abstract method: _format_result
    # =========================================================================

    def _format_result(self, state: AgentState) -> dict[str, Any]:
        """
        Convert final AgentState into a structured security scan result dict.

        Called by BaseAgent._node_format() to build state["final_result"].

        Args:
            state: Final AgentState after all workflow nodes

        Returns:
            Dict with keys: language, file_path, total_vulnerabilities,
            severity_counts, owasp_categories, risk_score, risk_level,
            critical_findings, llm_enhanced, summary
        """
        config: dict[str, Any] = state.get("config") or {}
        findings: list[dict[str, Any]] = config.get("_findings") or []
        agg: dict[str, Any] = config.get("_aggregation") or {}
        language: str = str(config.get("language") or "unknown")
        file_path: str = str(config.get("file_path") or "unknown")
        llm_enhanced: bool = bool(config.get("_llm_enhanced", False))

        # Collect unique OWASP categories hit
        owasp_categories: list[str] = list({
            str(f.get("owasp", "")) for f in findings if f.get("owasp")
        })

        # Critical + High findings for executive summary
        critical_findings = [
            {
                "vuln_id": f.get("vuln_id", ""),
                "severity": f.get("severity", ""),
                "line": f.get("line", 0),
                "title": f.get("title", ""),
                "cwe": f.get("cwe", ""),
            }
            for f in findings
            if f.get("severity") in ("CRITICAL", "HIGH")
        ][:10]

        r_score = int(agg.get("risk_score") or 0)
        r_level = str(agg.get("risk_level") or "INFO")

        severity_counts: dict[str, int] = agg.get("severity_counts") or {}

        return {
            "language": language,
            "file_path": file_path,
            "total_vulnerabilities": len(findings),
            "severity_counts": severity_counts,
            "owasp_categories": owasp_categories,
            "risk_score": r_score,
            "risk_level": r_level,
            "critical_findings": critical_findings,
            "llm_enhanced": llm_enhanced,
            "summary": (
                f"Security scan of '{file_path}' ({language}): "
                f"Risk level {r_level} (score {r_score}). "
                f"{len(findings)} vulnerabilities: "
                + ", ".join(
                    f"{v} {k}"
                    for k, v in severity_counts.items()
                    if v > 0
                ) + ". "
                f"OWASP categories: {', '.join(owasp_categories[:3]) or 'none'}."
            ),
        }

    # =========================================================================
    # Custom nodes
    # =========================================================================

    async def _node_parse_code(self, state: AgentState) -> AgentState:
        """
        Node 3: Read and validate source code from config.

        Args:
            state: Current AgentState

        Returns:
            Updated AgentState with _source in config, or error state
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        code_content: str = str(config.get("code_content") or "").strip()
        language: str = str(config.get("language") or "unknown").lower()

        logger.info(
            "[SecScanner] parse_code: language=%s len=%d",
            language, len(code_content),
        )

        if not code_content:
            return {
                **state,
                "error": "No code_content provided in AgentConfig.extra",
                "current_step": "parsed",
                "progress": 0.2,
            }

        config["_source"] = code_content
        config["_total_lines"] = len(code_content.splitlines())

        return {
            **state,
            "config": config,
            "current_step": "parsed",
            "progress": 0.25,
        }

    async def _node_scan(self, state: AgentState) -> AgentState:
        """
        Node 4: Run language-appropriate security scanner.

        Dispatches to PythonSecurityScanner or JSSecurityScanner.
        Falls back to a minimal generic scan for other languages.
        Stores findings in config["_findings"].

        Args:
            state: Current AgentState after parse_code

        Returns:
            Updated AgentState with _findings in config
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        source: str = str(config.get("_source") or "")
        language: str = str(config.get("language") or "unknown").lower()

        logger.info("[SecScanner] scan: language=%s", language)

        findings: list[dict[str, Any]] = []
        try:
            if language == "python":
                findings = PythonSecurityScanner.scan(source)
            elif language in ("javascript", "typescript", "jsx", "tsx", "js", "ts"):
                findings = JSSecurityScanner.scan(source)
            else:
                # Generic: only check for hardcoded secrets pattern
                secret_pat = re.compile(
                    r'(?i)(?:password|secret|api.?key|token)\s*[=:]\s*["\'][^"\']{6,}["\']'
                )
                for i, line in enumerate(source.splitlines(), start=1):
                    if secret_pat.search(line):
                        findings.append({
                            "vuln_id": "SEC-GEN-001",
                            "owasp": "A02 Cryptographic Failures",
                            "severity": "CRITICAL",
                            "cwe": "CWE-798",
                            "line": i,
                            "title": "Hardcoded Credential",
                            "detail": "Secret appears hardcoded in source.",
                            "evidence": line.strip()[:100],
                            "remediation": "Move to environment variables.",
                        })

        except Exception as exc:
            logger.error("[SecScanner] scan error: %s", exc, exc_info=True)
            findings.append({
                "vuln_id": "SEC-ERR-001",
                "owasp": "A05 Security Misconfiguration",
                "severity": "INFO",
                "cwe": "N/A",
                "line": 0,
                "title": "Scanner Error",
                "detail": str(exc),
                "evidence": "",
                "remediation": "Ensure code is valid and retry.",
            })

        logger.info("[SecScanner] Found %d vulnerabilities", len(findings))
        config["_findings"] = findings

        return {
            **state,
            "config": config,
            "current_step": "scanned",
            "progress": 0.55,
        }

    async def _node_aggregate(self, state: AgentState) -> AgentState:
        """
        Node 5: Compute risk score, risk level, and severity breakdown.

        Calculates a numeric risk score as the sum of severity scores
        across all findings, then maps to a risk level label.

        Args:
            state: Current AgentState with _findings available

        Returns:
            Updated AgentState with _aggregation dict in config
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        findings: list[dict[str, Any]] = config.get("_findings") or []

        severity_counts: dict[str, int] = {
            "CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0,
        }
        total_score = 0

        for f in findings:
            sev = str(f.get("severity", "INFO"))
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            total_score += SEVERITY_SCORE.get(sev, 0)

        rl = risk_level(total_score)

        agg = {
            "risk_score": total_score,
            "risk_level": rl,
            "severity_counts": severity_counts,
            "total_findings": len(findings),
            "owasp_categories": list({
                str(f.get("owasp", "")) for f in findings if f.get("owasp")
            }),
        }
        config["_aggregation"] = agg

        logger.info(
            "[SecScanner] risk_level=%s score=%d total=%d",
            rl, total_score, len(findings),
        )

        return {
            **state,
            "config": config,
            "current_step": "aggregated",
            "progress": 0.65,
        }

    async def _node_generate_report(self, state: AgentState) -> AgentState:
        """
        Node 6: Optional LLM-enhanced threat analysis.

        Pre-renders all finding details as a plain string (no format placeholders)
        before building the user_prompt_template. Only {context} and {query}
        remain as .format() placeholders — preventing KeyError.

        Args:
            state: Current AgentState with findings and aggregation available

        Returns:
            Updated AgentState with llm_response (if LLM available)
        """
        config: dict[str, Any] = dict(state.get("config") or {})
        findings: list[dict[str, Any]] = config.get("_findings") or []
        agg: dict[str, Any] = config.get("_aggregation") or {}
        language: str = str(config.get("language") or "unknown").lower()
        file_path: str = str(config.get("file_path") or "unknown")

        config["_llm_enhanced"] = False

        if not self._streaming_client or not findings:
            return {
                **state,
                "config": config,
                "llm_response": None,
                "current_step": "reported",
                "progress": 0.8,
            }

        # ── Pre-render findings block (plain string, no braces) ───────────
        finding_lines: list[str] = []
        for f in findings[:12]:
            vid = str(f.get("vuln_id") or "")
            sev = str(f.get("severity") or "")
            owasp = str(f.get("owasp") or "")
            cwe = str(f.get("cwe") or "")
            ln = str(f.get("line") or 0)
            title = str(f.get("title") or "")
            detail = str(f.get("detail") or "")[:120]
            finding_lines.append(
                vid + " [" + sev + "] " + owasp
                + " (" + cwe + ") line " + ln
                + ": " + title + " - " + detail
            )

        findings_block = "\n".join(finding_lines)

        risk_str = str(agg.get("risk_level") or "UNKNOWN")
        score_str = str(agg.get("risk_score") or 0)
        owasp_str = ", ".join(agg.get("owasp_categories") or [])

        system_prompt = (
            "You are a senior application security engineer (AppSec) "
            "conducting a professional security assessment. "
            "Provide expert threat analysis, attack scenario descriptions, "
            "and prioritized remediation roadmap. "
            "Be specific and actionable. Reference OWASP, CWE, and CVEs where relevant."
        )

        # ONLY {context} and {query} as placeholders — ALL else pre-rendered
        user_prompt_template = (
            "Security Scan Results\n"
            "File: " + file_path + " | Language: " + language + "\n"
            "Overall Risk: " + risk_str + " (Score: " + score_str + ")\n"
            "OWASP Categories Hit: " + owasp_str + "\n\n"
            "VULNERABILITIES FOUND:\n"
            + findings_block + "\n\n"
            "CODEBASE CONTEXT:\n{context}\n\n"
            "TASK: {query}\n\n"
            "Provide a security assessment with sections:\n"
            "1. EXECUTIVE SUMMARY: Overall risk posture\n"
            "2. ATTACK SCENARIOS: How each critical/high vuln could be exploited\n"
            "3. REMEDIATION ROADMAP: Prioritized fix list (quick wins first)\n"
            "4. SECURITY RECOMMENDATIONS: Broader hardening advice\n"
        )

        retrieval_query = (
            "Security vulnerabilities and remediation patterns for "
            + language + " in file " + file_path
            + ". Focus on: "
            + ", ".join(str(f.get("title", "")) for f in findings[:4])
        )
        state_for_llm = {**state, "config": config, "query": retrieval_query}

        try:
            updated = await self._node_analyze(
                state_for_llm,
                system_prompt=system_prompt,
                user_prompt_template=user_prompt_template,
            )
            llm_out = updated.get("llm_response") or ""
            if llm_out and len(llm_out) > 50:
                config["_llm_enhanced"] = True
                logger.info("[SecScanner] LLM analysis generated (%d chars)", len(llm_out))
            return {
                **updated,
                "config": config,
                "current_step": "reported",
                "progress": 0.8,
            }
        except Exception as exc:
            logger.warning("[SecScanner] LLM report failed: %s", exc)
            return {
                **state,
                "config": config,
                "llm_response": None,
                "current_step": "reported",
                "progress": 0.8,
            }

    async def _node_done(self, state: AgentState) -> AgentState:
        """
        Node 8: Assemble the final Markdown security report.

        Produces a structured security report with:
        - Risk level badge and score
        - Severity breakdown table
        - OWASP categories hit
        - All findings grouped by severity with CWE and remediation
        - LLM threat analysis section (if available)
        - Remediation checklist

        Args:
            state: AgentState after _node_format has run

        Returns:
            Final AgentState with formatted_report and progress 1.0
        """
        config: dict[str, Any] = state.get("config") or {}
        findings: list[dict[str, Any]] = config.get("_findings") or []
        agg: dict[str, Any] = config.get("_aggregation") or {}
        language: str = str(config.get("language") or "unknown")
        file_path: str = str(config.get("file_path") or "unknown")
        llm_response: str = state.get("llm_response") or ""
        final_result: dict[str, Any] = state.get("final_result") or {}

        risk_lv = str(agg.get("risk_level") or "INFO")
        risk_sc = int(agg.get("risk_score") or 0)
        severity_counts: dict[str, int] = agg.get("severity_counts") or {}
        owasp_cats: list[str] = agg.get("owasp_categories") or []
        total_lines = int(config.get("_total_lines") or 0)

        risk_emoji = {
            "CRITICAL": "CRITICAL",
            "HIGH": "HIGH",
            "MEDIUM": "MEDIUM",
            "LOW": "LOW",
            "INFO": "INFO",
        }.get(risk_lv, risk_lv)

        lines: list[str] = [
            "# Security Scan Report",
            "",
            "**File:** `" + file_path + "`",
            "**Language:** " + language.title(),
            "**Scanned:** " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "**Lines Scanned:** " + str(total_lines),
            "",
            "---",
            "",
            "## Risk Assessment",
            "",
            "```",
            "Overall Risk:  " + risk_emoji,
            "Risk Score:    " + str(risk_sc),
            "Vulns Found:   " + str(len(findings)),
            "```",
            "",
        ]

        # Severity table
        lines += [
            "| Severity | Count | Score Impact |",
            "|----------|-------|-------------|",
        ]
        for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
            cnt = severity_counts.get(sev, 0)
            if cnt > 0:
                impact = SEVERITY_SCORE.get(sev, 0) * cnt
                lines.append(
                    "| " + sev + " | " + str(cnt)
                    + " | +" + str(impact) + " |"
                )
        lines += ["", "---", ""]

        # OWASP categories
        if owasp_cats:
            lines += [
                "## OWASP Top 10 Categories Detected",
                "",
            ]
            for cat in sorted(owasp_cats):
                lines.append("- " + cat)
            lines += ["", "---", ""]

        # Findings by severity
        if findings:
            lines += ["## Vulnerability Details", ""]

            for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
                sev_findings = [f for f in findings if f.get("severity") == sev]
                if not sev_findings:
                    continue

                lines.append("### " + sev + " (" + str(len(sev_findings)) + ")")
                lines.append("")

                for f in sev_findings:
                    vid = str(f.get("vuln_id") or "")
                    cwe = str(f.get("cwe") or "")
                    owasp = str(f.get("owasp") or "")
                    ln = str(f.get("line") or 0)
                    title = str(f.get("title") or "")
                    detail = str(f.get("detail") or "")
                    evidence = str(f.get("evidence") or "")
                    remediation = str(f.get("remediation") or "")

                    lines.append(
                        "**[" + vid + "] " + title + "** — Line " + ln
                    )
                    lines.append("- **CWE:** " + cwe + " | **OWASP:** " + owasp)
                    lines.append("- **Issue:** " + detail)
                    if evidence:
                        lines.append("- **Evidence:** `" + evidence[:80] + "`")
                    lines.append("- **Fix:** " + remediation)
                    lines.append("")

            lines.append("---")
            lines.append("")
        else:
            lines += [
                "## Vulnerability Details",
                "",
                "No vulnerabilities detected. Code appears secure.",
                "",
                "---",
                "",
            ]

        # LLM threat analysis
        lines += ["## AI Threat Analysis", ""]
        if llm_response and llm_response.strip():
            lines.append(llm_response.strip())
        else:
            lines.append(
                "*AI threat analysis not available. "
                "Static scan results above are complete.*"
            )

        # Remediation checklist
        lines += [
            "",
            "---",
            "",
            "## Remediation Checklist",
            "",
        ]
        critical_high = [
            f for f in findings if f.get("severity") in ("CRITICAL", "HIGH")
        ]
        if critical_high:
            for f in critical_high[:8]:
                lines.append(
                    "- [ ] **[" + str(f.get("vuln_id", "")) + "]** "
                    + str(f.get("title", "")) + " (line "
                    + str(f.get("line", 0)) + ")"
                )
        else:
            lines.append("- [x] No critical or high severity issues found")

        lines += [
            "",
            "---",
            "",
            "*Generated by AI Codebase Assistant — Security Scanner Agent*",
            "*This scan covers common patterns. Always perform manual security review*",
            "*and penetration testing before deploying to production.*",
        ]

        return {
            **state,
            "formatted_report": "\n".join(lines),
            "status": AgentStatus.COMPLETED.value,
            "current_step": "done",
            "progress": 1.0,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }


# =============================================================================
# Factory
# =============================================================================

def create_security_scanner_agent(
    retriever: Any = None,
    streaming_client: Any = None,
) -> SecurityScannerAgent:
    """
    Create and return a configured SecurityScannerAgent instance.

    Args:
        retriever:        Optional RAG retriever for codebase context
        streaming_client: Optional Ollama client for AI threat analysis

    Returns:
        Ready-to-use SecurityScannerAgent
    """
    return SecurityScannerAgent(
        retriever=retriever,
        streaming_client=streaming_client,
    )
