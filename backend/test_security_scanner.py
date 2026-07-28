"""
Step 24 Test Suite - SecurityScannerAgent
Run from backend/ directory with venv activated:
    cd backend
    python test_security_scanner.py
"""

import asyncio
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
def test_python_scanner_critical() -> None:
    print("[1] PythonSecurityScanner - critical vulnerabilities")
    from app.core.agents.security_scanner import PythonSecurityScanner

    code = (
        "import pickle\n"
        "import os\n"
        "import random\n\n"
        "password = 'super_secret_123'\n\n"
        "def run_cmd(user_input):\n"
        "    os.system(user_input)\n\n"
        "def load_data(data):\n"
        "    return pickle.loads(data)\n\n"
        "def execute_code(code_str):\n"
        "    eval(code_str)\n\n"
        "def get_token():\n"
        "    return str(random.random())\n"
    )

    findings = PythonSecurityScanner.scan(code)
    vuln_ids = [f["vuln_id"] for f in findings]
    severities = [f["severity"] for f in findings]

    print(f"  Found {len(findings)} vulnerabilities")
    print(f"  Vuln IDs: {vuln_ids}")
    print(f"  Severities: {severities}")

    assert "SEC-PY-001" in vuln_ids, f"SEC-PY-001 (credential) missing: {vuln_ids}"
    assert "SEC-PY-003" in vuln_ids, f"SEC-PY-003 (cmd injection) missing: {vuln_ids}"
    assert "SEC-PY-005" in vuln_ids, f"SEC-PY-005 (pickle) missing: {vuln_ids}"
    assert "SEC-PY-004" in vuln_ids, f"SEC-PY-004 (eval) missing: {vuln_ids}"
    assert "SEC-PY-009" in vuln_ids, f"SEC-PY-009 (random) missing: {vuln_ids}"
    assert "CRITICAL" in severities, "Expected CRITICAL findings"

    ok("PythonSecurityScanner critical vulns")


# ---------------------------------------------------------------------------
def test_python_scanner_crypto() -> None:
    print("[2] PythonSecurityScanner - crypto issues")
    from app.core.agents.security_scanner import PythonSecurityScanner

    code = (
        "import hashlib\n"
        "import yaml\n\n"
        "def hash_password(pwd):\n"
        "    return hashlib.md5(pwd.encode()).hexdigest()\n\n"
        "def load_config(data):\n"
        "    return yaml.load(data)\n\n"
        "DEBUG = True\n"
    )

    findings = PythonSecurityScanner.scan(code)
    vuln_ids = [f["vuln_id"] for f in findings]
    print(f"  Vuln IDs: {vuln_ids}")

    assert "SEC-PY-006" in vuln_ids, f"SEC-PY-006 (weak crypto) missing: {vuln_ids}"
    assert "SEC-PY-005b" in vuln_ids, f"SEC-PY-005b (yaml.load) missing: {vuln_ids}"
    assert "SEC-PY-010" in vuln_ids, f"SEC-PY-010 (debug) missing: {vuln_ids}"

    ok("PythonSecurityScanner crypto issues")


# ---------------------------------------------------------------------------
def test_python_scanner_clean() -> None:
    print("[3] PythonSecurityScanner - clean code")
    from app.core.agents.security_scanner import PythonSecurityScanner

    clean_code = (
        "import os\n"
        "import hashlib\n"
        "import secrets\n\n"
        "DB_URL = os.environ.get('DATABASE_URL', '')\n"
        "API_KEY = os.environ.get('API_KEY', '')\n\n"
        "def hash_data(data: str) -> str:\n"
        "    return hashlib.sha256(data.encode()).hexdigest()\n\n"
        "def generate_token() -> str:\n"
        "    return secrets.token_hex(32)\n"
    )

    findings = PythonSecurityScanner.scan(clean_code)
    critical = [f for f in findings if f["severity"] == "CRITICAL"]
    print(f"  Total findings: {len(findings)} | Critical: {len(critical)}")

    assert len(critical) == 0, f"Clean code should have no CRITICAL: {critical}"

    ok("PythonSecurityScanner clean code")


# ---------------------------------------------------------------------------
def test_js_scanner() -> None:
    print("[4] JSSecurityScanner")
    from app.core.agents.security_scanner import JSSecurityScanner

    code = (
        "const jwtSecret = 'my-super-secret-jwt-key-123';\n"
        "const password = 'admin123';\n\n"
        "function runCode(userInput) {\n"
        "    eval(userInput);\n"
        "}\n\n"
        "function renderContent(html) {\n"
        "    document.getElementById('app').innerHTML = html;\n"
        "}\n\n"
        "function getRandomId() {\n"
        "    return Math.random().toString(36);\n"
        "}\n\n"
        "const token = localStorage.getItem('auth_token');\n"
        "localStorage.setItem('password', userPwd);\n"
    )

    findings = JSSecurityScanner.scan(code)
    vuln_ids = [f["vuln_id"] for f in findings]
    print(f"  Found {len(findings)} vulns: {vuln_ids}")

    assert "SEC-JS-001" in vuln_ids, f"SEC-JS-001 (credential) missing"
    assert "SEC-JS-002" in vuln_ids, f"SEC-JS-002 (eval) missing"
    assert "SEC-JS-003" in vuln_ids, f"SEC-JS-003 (innerHTML) missing"
    assert "SEC-JS-005" in vuln_ids, f"SEC-JS-005 (Math.random) missing"
    assert "SEC-JS-006" in vuln_ids, f"SEC-JS-006 (JWT secret) missing"

    ok("JSSecurityScanner")


# ---------------------------------------------------------------------------
def test_risk_level() -> None:
    print("[5] risk_level calculation")
    from app.core.agents.security_scanner import risk_level

    # RISK_LEVELS = [(80,CRITICAL),(50,HIGH),(25,MEDIUM),(10,LOW),(0,INFO)]
    assert risk_level(0)   == "INFO",    f"Expected INFO for 0, got {risk_level(0)}"
    assert risk_level(5)   == "INFO",    f"Expected INFO for 5, got {risk_level(5)}"
    assert risk_level(10)  == "LOW",     f"Expected LOW for 10, got {risk_level(10)}"
    assert risk_level(15)  == "LOW",     f"Expected LOW for 15, got {risk_level(15)}"
    assert risk_level(25)  == "MEDIUM",  f"Expected MEDIUM for 25, got {risk_level(25)}"
    assert risk_level(30)  == "MEDIUM",  f"Expected MEDIUM for 30, got {risk_level(30)}"
    assert risk_level(50)  == "HIGH",    f"Expected HIGH for 50, got {risk_level(50)}"
    assert risk_level(55)  == "HIGH",    f"Expected HIGH for 55, got {risk_level(55)}"
    assert risk_level(80)  == "CRITICAL",f"Expected CRITICAL for 80, got {risk_level(80)}"
    assert risk_level(100) == "CRITICAL",f"Expected CRITICAL for 100, got {risk_level(100)}"

    print(f"  Thresholds: INFO<10, LOW<25, MED<50, HIGH<80, CRIT>=80 — all correct")
    ok("risk_level")


# ---------------------------------------------------------------------------
def test_agent_instantiation() -> None:
    print("[6] SecurityScannerAgent instantiation")
    from app.core.agents.security_scanner import SecurityScannerAgent

    agent = SecurityScannerAgent()
    print(f"  agent_type   = {agent.agent_type}")
    print(f"  display_name = {agent.display_name}")
    assert agent.agent_type == "security_scanner"
    assert "Security Scanner" in agent.display_name

    ok("instantiation")


# ---------------------------------------------------------------------------
def test_build_graph() -> None:
    print("[7] _build_graph")
    from app.core.agents.security_scanner import SecurityScannerAgent

    agent = SecurityScannerAgent()
    graph = agent._get_graph()
    print(f"  type: {type(graph).__name__}")
    assert graph is not None

    ok("_build_graph")


# ---------------------------------------------------------------------------
def test_format_result() -> None:
    print("[8] _format_result")
    from app.core.agents.security_scanner import SecurityScannerAgent

    agent = SecurityScannerAgent()
    mock_state = {
        "config": {
            "language": "python",
            "file_path": "app.py",
            "_findings": [
                {
                    "vuln_id": "SEC-PY-001", "severity": "CRITICAL",
                    "owasp": "A02 Cryptographic Failures", "cwe": "CWE-798",
                    "line": 5, "title": "Hardcoded Credential",
                    "detail": "Password found", "evidence": "password='secret'",
                    "remediation": "Use env vars",
                },
                {
                    "vuln_id": "SEC-PY-003", "severity": "CRITICAL",
                    "owasp": "A03 Injection", "cwe": "CWE-78",
                    "line": 10, "title": "Command Injection",
                    "detail": "os.system found", "evidence": "os.system(cmd)",
                    "remediation": "Use subprocess list",
                },
                {
                    "vuln_id": "SEC-PY-009", "severity": "MEDIUM",
                    "owasp": "A02 Cryptographic Failures", "cwe": "CWE-338",
                    "line": 15, "title": "Insecure Random",
                    "detail": "random.random", "evidence": "random.random()",
                    "remediation": "Use secrets",
                },
            ],
            "_aggregation": {
                "risk_score": 88,
                "risk_level": "CRITICAL",
                "severity_counts": {
                    "CRITICAL": 2, "HIGH": 0, "MEDIUM": 1, "LOW": 0, "INFO": 0
                },
                "total_findings": 3,
                "owasp_categories": ["A02 Cryptographic Failures", "A03 Injection"],
            },
            "_llm_enhanced": False,
        },
        "llm_response": None,
    }

    result = agent._format_result(mock_state)
    print(f"  keys: {sorted(result.keys())}")
    print(f"  summary: {result['summary']}")

    assert result["total_vulnerabilities"] == 3
    assert result["risk_level"] == "CRITICAL"
    assert result["risk_score"] == 88
    assert len(result["critical_findings"]) == 2
    assert "A03 Injection" in result["owasp_categories"]

    ok("_format_result")


# ---------------------------------------------------------------------------
def test_factory_registry() -> None:
    print("[9] factory + registry")
    from app.core.agents import AGENT_REGISTRY
    from app.core.agents.security_scanner import create_security_scanner_agent

    agent = create_security_scanner_agent()
    assert agent.agent_type == "security_scanner"

    assert "security_scanner" in AGENT_REGISTRY
    assert AGENT_REGISTRY["security_scanner"]["class"] == "SecurityScannerAgent"
    print(f"  Registry: {list(AGENT_REGISTRY.keys())}")

    ok("factory + registry")


# ---------------------------------------------------------------------------
async def test_full_run_vulnerable_python() -> None:
    print("[10] Full agent run - vulnerable Python (no LLM)")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.security_scanner import SecurityScannerAgent

    agent = SecurityScannerAgent(retriever=None, streaming_client=None)

    config = AgentConfig(
        project_id="sec-test-proj",
        user_id="sec-test-user",
        query="Scan for security vulnerabilities",
        model="tinyllama",
        extra={
            "code_content": (
                "import os, pickle, hashlib, random\n\n"
                "db_password = 'admin_secret_123'\n\n"
                "def run(cmd):\n"
                "    os.system(cmd)\n\n"
                "def deserialize(data):\n"
                "    return pickle.loads(data)\n\n"
                "def weak_hash(s):\n"
                "    return hashlib.md5(s.encode()).hexdigest()\n\n"
                "DEBUG = True\n"
            ),
            "language": "python",
            "file_path": "vulnerable_app.py",
        },
    )

    result = await agent.run(config)

    print(f"  status:     {result.status}")
    print(f"  elapsed_ms: {result.elapsed_ms:.1f}")
    print(f"  error:      {result.error}")

    if result.result:
        r = result.result
        print(f"  risk_level:  {r.get('risk_level')}")
        print(f"  risk_score:  {r.get('risk_score')}")
        print(f"  total_vulns: {r.get('total_vulnerabilities')}")
        print(f"  summary:     {r.get('summary')}")

    if result.report:
        print(f"  report ({len(result.report)} chars) preview:")
        for line in result.report[:600].splitlines():
            print("    " + line)

    assert result.status == AgentStatus.COMPLETED, \
        f"Expected COMPLETED, got {result.status}. Error: {result.error}"
    assert result.error is None
    assert result.result is not None
    assert result.report is not None
    assert "# Security Scan Report" in result.report
    assert result.result["total_vulnerabilities"] >= 3
    assert result.result["risk_level"] in ("CRITICAL", "HIGH", "MEDIUM")
    assert "CRITICAL" in result.report

    ok("full agent run vulnerable Python COMPLETED")


# ---------------------------------------------------------------------------
async def test_full_run_clean_code() -> None:
    print("[11] Full agent run - clean code has low risk (no LLM)")
    from app.core.agents.base_agent import AgentConfig, AgentStatus
    from app.core.agents.security_scanner import SecurityScannerAgent

    agent = SecurityScannerAgent(retriever=None, streaming_client=None)

    config = AgentConfig(
        project_id="sec-clean-proj",
        user_id="sec-clean-user",
        query="Scan for security vulnerabilities",
        model="tinyllama",
        extra={
            "code_content": (
                "import os\n"
                "import secrets\n"
                "import hashlib\n\n"
                "API_URL = os.environ.get('API_URL', 'https://api.example.com')\n"
                "SECRET_KEY = os.environ.get('SECRET_KEY', '')\n\n"
                "def generate_id() -> str:\n"
                "    return secrets.token_hex(16)\n\n"
                "def hash_data(data: str) -> str:\n"
                "    return hashlib.sha256(data.encode()).hexdigest()\n"
            ),
            "language": "python",
            "file_path": "secure_utils.py",
        },
    )

    result = await agent.run(config)

    print(f"  status: {result.status}")
    if result.result:
        print(f"  risk_level: {result.result.get('risk_level')}")
        print(f"  total_vulns: {result.result.get('total_vulnerabilities')}")

    assert result.status == AgentStatus.COMPLETED
    total = result.result.get("total_vulnerabilities") or 0
    assert total < 3, f"Clean code should have < 3 vulns, got {total}"

    ok(f"clean code: {total} vulns, risk={result.result.get('risk_level')}")


# ---------------------------------------------------------------------------
async def main() -> None:
    print("=" * 60)
    print("Step 24 - SecurityScannerAgent Test Suite")
    print("=" * 60)
    print()

    sync_fns = [
        test_python_scanner_critical,
        test_python_scanner_crypto,
        test_python_scanner_clean,
        test_js_scanner,
        test_risk_level,
        test_agent_instantiation,
        test_build_graph,
        test_format_result,
        test_factory_registry,
    ]
    async_fns = [
        test_full_run_vulnerable_python,
        test_full_run_clean_code,
    ]

    for fn in sync_fns:
        try:
            fn()
        except Exception as exc:
            fail(fn.__name__, exc)
        print()

    for fn in async_fns:
        try:
            await fn()
        except Exception as exc:
            fail(fn.__name__, exc)
        print()

    print("=" * 60)
    print(f"Results: {PASS} passed | {FAIL} failed")
    print("ALL TESTS PASSED" if FAIL == 0 else "SOME TESTS FAILED")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())

