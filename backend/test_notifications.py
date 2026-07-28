"""
Step 31 Test Suite - Email Notification System
Run from backend/ directory:
    cd backend
    python test_notifications.py
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
def test_smtp_config() -> None:
    print("[1] SMTPConfig loads from environment")
    from app.services.notification_service import SMTPConfig

    config = SMTPConfig()
    print(f"  host:          {config.host}")
    print(f"  port:          {config.port}")
    print(f"  from_email:    {config.from_email}")
    print(f"  enabled:       {config.enabled}")
    print(f"  is_configured: {config.is_configured}")

    assert isinstance(config.host, str)
    assert isinstance(config.port, int)
    assert config.port > 0
    assert isinstance(config.is_configured, bool)

    d = config.to_dict()
    assert "password" not in d or d["password"] in ("***", "(not set)")
    print(f"  to_dict keys: {list(d.keys())}")

    ok("SMTPConfig")


# ---------------------------------------------------------------------------
def test_email_sender_dev_mode() -> None:
    print("[2] EmailSender dev mode (SMTP disabled)")
    from app.services.notification_service import EmailSender, SMTPConfig

    # Create config with SMTP disabled
    config = SMTPConfig()
    config.enabled = False

    sender = EmailSender(config=config)
    result = sender.send(
        to_email="test@example.com",
        subject="Test Email",
        html_body="<p>Hello World</p>",
        plaintext_body="Hello World",
    )

    print(f"  result: {result}")
    assert result["success"] is True
    assert result["mode"] == "logged"
    assert result["to_email"] == "test@example.com"

    ok("EmailSender dev mode (logs, does not send)")


# ---------------------------------------------------------------------------
def test_agent_complete_template() -> None:
    print("[3] build_agent_complete_email template")
    from app.services.notification_service import build_agent_complete_email

    subject, html, plaintext = build_agent_complete_email(
        agent_display_name="Security Scanner",
        file_path="src/auth.py",
        quality_score=75,
        total_findings=12,
        critical_count=3,
        elapsed_seconds=42.5,
        project_url="http://localhost:3000/projects/p1",
    )

    print(f"  subject: {subject}")
    print(f"  html length: {len(html)} chars")
    print(f"  plaintext length: {len(plaintext)} chars")

    assert "Security Scanner" in subject
    assert "auth.py" in subject
    assert "<!DOCTYPE html>" in html
    assert "75/100" in html  # quality score
    assert "12" in html       # total findings
    assert "3" in html        # critical count
    assert len(plaintext) > 50

    ok("agent_complete email template")


# ---------------------------------------------------------------------------
def test_indexing_complete_template() -> None:
    print("[4] build_indexing_complete_email template")
    from app.services.notification_service import build_indexing_complete_email

    subject, html, plaintext = build_indexing_complete_email(
        project_name="My Awesome Project",
        total_files=200,
        indexed_count=195,
        failed_count=5,
        total_chunks=1580,
        elapsed_seconds=120.0,
        project_url="http://localhost:3000/projects/p1",
    )

    print(f"  subject: {subject}")
    assert "My Awesome Project" in subject
    assert "ready" in subject.lower()
    assert "195" in html
    assert "1,580" in html  # formatted with comma
    assert "97.5" in html   # success rate

    ok("indexing_complete email template")


# ---------------------------------------------------------------------------
def test_security_alert_template() -> None:
    print("[5] build_security_alert_email template")
    from app.services.notification_service import build_security_alert_email

    top_findings = [
        {
            "vuln_id": "SEC-PY-001",
            "severity": "CRITICAL",
            "title": "Hardcoded Credential",
            "cwe": "CWE-798",
        },
        {
            "vuln_id": "SEC-PY-004",
            "severity": "CRITICAL",
            "title": "eval() Usage",
            "cwe": "CWE-95",
        },
    ]

    subject, html, plaintext = build_security_alert_email(
        file_path="src/app.py",
        critical_count=2,
        high_count=3,
        top_findings=top_findings,
        project_url="http://localhost:3000/projects/p1/security",
    )

    print(f"  subject: {subject}")
    assert "SECURITY ALERT" in subject
    assert "2" in subject
    assert "SEC-PY-001" in html
    assert "Hardcoded Credential" in html
    assert "CWE-798" in html

    ok("security_alert email template")


# ---------------------------------------------------------------------------
def test_task_failed_template() -> None:
    print("[6] build_task_failed_email template")
    from app.services.notification_service import build_task_failed_email

    subject, html, plaintext = build_task_failed_email(
        task_type="Bug Finder Analysis",
        agent_id="bug_finder",
        error_message="Connection refused: LLM service unavailable at localhost:11434",
        project_url="http://localhost:3000/projects/p1",
    )

    print(f"  subject: {subject}")
    assert "Task Failed" in subject
    assert "Bug Finder" in subject
    assert "Connection refused" in html
    assert "bug_finder" in html.lower() or "bug_finder" in plaintext

    ok("task_failed email template")


# ---------------------------------------------------------------------------
def test_unsubscribe_token() -> None:
    print("[7] Unsubscribe token generation")
    from app.services.notification_service import generate_unsubscribe_token

    token1 = generate_unsubscribe_token("user-001", "test@example.com")
    token2 = generate_unsubscribe_token("user-001", "test@example.com")
    token3 = generate_unsubscribe_token("user-002", "test@example.com")

    print(f"  token1: {token1}")
    print(f"  token2: {token2}")
    print(f"  token3 (diff user): {token3}")

    # Same inputs = same token (deterministic)
    assert token1 == token2, "Token should be deterministic"
    # Different user = different token
    assert token1 != token3, "Different users should have different tokens"
    # Token format
    assert len(token1) == 32
    assert all(c in "0123456789abcdef" for c in token1)

    ok("unsubscribe token generation")


# ---------------------------------------------------------------------------
def test_rate_limiter_no_redis() -> None:
    print("[8] EmailRateLimiter without Redis (graceful fallback)")
    from app.services.notification_service import EmailRateLimiter

    # Without Redis, should allow (graceful fallback)
    result = EmailRateLimiter.is_allowed("test-user-xyz", "agent_complete")
    print(f"  is_allowed (no Redis): {result}")
    assert isinstance(result, bool)

    remaining = EmailRateLimiter.get_remaining("test-user-xyz")
    print(f"  get_remaining (no Redis): {remaining}")
    assert isinstance(remaining, int)
    assert remaining >= 0

    ok("rate limiter graceful fallback")


# ---------------------------------------------------------------------------
def test_notification_service_dev_mode() -> None:
    print("[9] NotificationService full send (dev mode)")
    from app.services.notification_service import (
        NotificationService,
        EmailSender,
        SMTPConfig,
    )

    # Use a sender with SMTP disabled
    config = SMTPConfig()
    config.enabled = False
    sender = EmailSender(config=config)
    service = NotificationService(sender=sender)

    result = service.send_agent_complete(
        to_email="dev@example.com",
        user_id="test-user-001",
        agent_display_name="Code Reviewer",
        file_path="main.py",
        quality_score=85,
        total_findings=5,
        critical_count=0,
        elapsed_seconds=30.0,
        project_id="proj-001",
    )

    print(f"  result: {result}")
    assert result["success"] is True
    assert result["mode"] in ("logged", "sent", "rate_limited")

    ok("NotificationService dev mode send")


# ---------------------------------------------------------------------------
def test_security_alert_skipped_low_findings() -> None:
    print("[10] Security alert skipped for low findings")
    from app.services.notification_service import (
        NotificationService,
        EmailSender,
        SMTPConfig,
    )

    config = SMTPConfig()
    config.enabled = False
    service = NotificationService(sender=EmailSender(config=config))

    # critical_count=0 and high_count < 3 should skip
    result = service.send_security_alert(
        to_email="dev@example.com",
        user_id="test-user-002",
        file_path="utils.py",
        critical_count=0,
        high_count=1,
        top_findings=[],
        project_id="proj-001",
    )

    print(f"  result: {result}")
    assert result["mode"] == "skipped"
    assert result["reason"] == "no critical findings"

    ok("security alert skipped for low findings")


# ---------------------------------------------------------------------------
def test_notification_tasks_import() -> None:
    print("[11] notification_tasks Celery import")
    from app.tasks.notification_tasks import (
        send_agent_complete_email,
        send_indexing_complete_email,
        send_security_alert_email,
        send_task_failed_email,
    )

    tasks = [
        send_agent_complete_email,
        send_indexing_complete_email,
        send_security_alert_email,
        send_task_failed_email,
    ]
    for task in tasks:
        print(f"  task: {task.name}")
        assert "notification_tasks" in task.name

    ok("notification_tasks imports")


# ---------------------------------------------------------------------------
def test_celery_task_registration() -> None:
    print("[12] Notification tasks registered in Celery")
    from app.tasks.celery_app import celery_app

    registered = list(celery_app.tasks.keys())
    expected = [
        "app.tasks.notification_tasks.send_agent_complete_email",
        "app.tasks.notification_tasks.send_indexing_complete_email",
        "app.tasks.notification_tasks.send_security_alert_email",
        "app.tasks.notification_tasks.send_task_failed_email",
    ]
    for name in expected:
        assert name in registered, \
            f"Task not registered: {name}"
        print(f"  Found: {name}")

    ok("notification tasks registered in Celery")


# ---------------------------------------------------------------------------
def test_api_router_import() -> None:
    print("[13] notifications API router")
    from app.api.v1.notifications import (
        router,
        NotificationPreferences,
        TestNotificationRequest,
    )

    print(f"  prefix: {router.prefix}")
    assert router.prefix == "/notifications"
    assert "notifications" in router.tags

    ok("notifications router imports")


# ---------------------------------------------------------------------------
def test_tasks_init_exports() -> None:
    print("[14] tasks/__init__.py exports notification tasks")
    from app.tasks import (
        send_agent_complete_email,
        send_indexing_complete_email,
        send_security_alert_email,
        send_task_failed_email,
    )

    assert callable(send_agent_complete_email)
    assert callable(send_indexing_complete_email)
    assert callable(send_security_alert_email)
    assert callable(send_task_failed_email)

    ok("tasks __init__ exports all notification tasks")


# ---------------------------------------------------------------------------
def test_html_template_is_valid_html() -> None:
    print("[15] HTML template produces valid structure")
    from app.services.notification_service import build_agent_complete_email

    _, html, _ = build_agent_complete_email(
        agent_display_name="Test Agent",
        file_path="test.py",
        quality_score=90,
        total_findings=2,
        critical_count=0,
        elapsed_seconds=10.0,
        project_url="http://localhost:3000/p/1",
    )

    # Basic HTML structure checks
    assert html.startswith("<!DOCTYPE html>")
    assert "<html" in html
    assert "</html>" in html
    assert "<head>" in html
    assert "<body>" in html
    assert "</body>" in html
    assert "AI Codebase Assistant" in html
    assert "unsubscribe" in html.lower()
    print(f"  HTML length: {len(html)} chars")
    print(f"  Has DOCTYPE: {html.startswith('<!DOCTYPE html>')}")
    print(f"  Has unsubscribe: {'unsubscribe' in html.lower()}")

    ok("HTML template valid structure")


# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 60)
    print("Step 31 - Email Notification System Test Suite")
    print("=" * 60)
    print()

    tests = [
        test_smtp_config,
        test_email_sender_dev_mode,
        test_agent_complete_template,
        test_indexing_complete_template,
        test_security_alert_template,
        test_task_failed_template,
        test_unsubscribe_token,
        test_rate_limiter_no_redis,
        test_notification_service_dev_mode,
        test_security_alert_skipped_low_findings,
        test_notification_tasks_import,
        test_celery_task_registration,
        test_api_router_import,
        test_tasks_init_exports,
        test_html_template_is_valid_html,
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
        print("Email notification system ready!")
        print()
        print("To enable real email sending, set these env vars:")
        print("  SMTP_ENABLED=true")
        print("  SMTP_HOST=smtp.gmail.com")
        print("  SMTP_PORT=587")
        print("  SMTP_USERNAME=your@gmail.com")
        print("  SMTP_PASSWORD=your-app-password-16chars")
        print("  SMTP_FROM_EMAIL=your@gmail.com")
        print("  SMTP_FROM_NAME=AI Codebase Assistant")

    import sys
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
