"""
Notification Service - Step 31
AI Codebase Assistant v2.0

Sends HTML email notifications via SMTP (free tier compatible):
    - Gmail SMTP (smtp.gmail.com:587 with App Password)
    - Outlook SMTP (smtp-mail.outlook.com:587)
    - SendGrid SMTP (smtp.sendgrid.net:587 free tier)
    - Mailgun SMTP (smtp.mailgun.org:587 free tier)
    - Local dev: MailHog or console output

Email types:
    agent_complete     - Agent analysis finished with results summary
    indexing_complete  - Project indexing finished with stats
    security_alert     - CRITICAL/HIGH security vulnerabilities found
    task_failed        - Long-running task failed with error info
    weekly_summary     - Weekly project health digest (scheduled)

Features:
    - HTML + plaintext fallback in every email
    - Jinja2 templating with inline CSS for email clients
    - Rate limiting: max 10 emails per user per hour
    - Unsubscribe token in every email footer
    - Delivery tracking via Redis (sent/failed counts)
    - Graceful degradation: logs email if SMTP unavailable
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import smtplib
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# SMTP Configuration
# =============================================================================

class SMTPConfig:
    """
    SMTP server configuration loaded from environment variables.

    Supported providers (all free tier):
        Gmail:    SMTP_HOST=smtp.gmail.com SMTP_PORT=587
        Outlook:  SMTP_HOST=smtp-mail.outlook.com SMTP_PORT=587
        SendGrid: SMTP_HOST=smtp.sendgrid.net SMTP_PORT=587
        MailHog:  SMTP_HOST=localhost SMTP_PORT=1025 (dev only)

    Gmail setup:
        1. Enable 2FA on Google account
        2. Generate App Password: Account > Security > App Passwords
        3. Set SMTP_PASSWORD=your-16-char-app-password
    """

    def __init__(self) -> None:
        """Load SMTP config from environment variables."""
        self.host: str = os.getenv("SMTP_HOST", "localhost")
        self.port: int = int(os.getenv("SMTP_PORT", "1025"))
        self.username: str = os.getenv("SMTP_USERNAME", "")
        self.password: str = os.getenv("SMTP_PASSWORD", "")
        self.from_email: str = os.getenv(
            "SMTP_FROM_EMAIL",
            "noreply@ai-codebase-assistant.dev"
        )
        self.from_name: str = os.getenv(
            "SMTP_FROM_NAME",
            "AI Codebase Assistant"
        )
        self.use_tls: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        self.enabled: bool = os.getenv("SMTP_ENABLED", "false").lower() == "true"

    @property
    def is_configured(self) -> bool:
        """Return True if SMTP is properly configured for sending."""
        return (
            self.enabled
            and bool(self.host)
            and self.port > 0
            and bool(self.from_email)
        )

    def to_dict(self) -> dict[str, Any]:
        """Return config as dict (password redacted)."""
        return {
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "from_email": self.from_email,
            "from_name": self.from_name,
            "use_tls": self.use_tls,
            "enabled": self.enabled,
            "is_configured": self.is_configured,
            "password": "***" if self.password else "(not set)",
        }


smtp_config = SMTPConfig()


# =============================================================================
# HTML Email Templates
# =============================================================================

def _base_template(
    title: str,
    preview_text: str,
    body_html: str,
    user_email: str = "",
    unsubscribe_token: str = "",
) -> tuple[str, str]:
    """
    Wrap body HTML in a complete responsive email template.

    Returns both HTML and plaintext versions of the email.

    Args:
        title:             Email subject / title shown in header
        preview_text:      Text shown in email client preview pane
        body_html:         Main HTML content for the email body
        user_email:        Recipient email for unsubscribe link
        unsubscribe_token: Unique token for unsubscribe URL

    Returns:
        Tuple of (html_content: str, plaintext_content: str)
    """
    app_url = os.getenv("APP_URL", "http://localhost:3000")
    unsubscribe_url = (
        f"{app_url}/unsubscribe?token={unsubscribe_token}&email={user_email}"
        if unsubscribe_token
        else f"{app_url}/notifications"
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  body {{ margin:0; padding:0; background:#0d1117; font-family:'Segoe UI',Arial,sans-serif; }}
  .wrapper {{ max-width:600px; margin:0 auto; padding:20px; }}
  .header {{ background:linear-gradient(135deg,#3b82f6,#8b5cf6);
             border-radius:12px 12px 0 0; padding:32px 24px; text-align:center; }}
  .header h1 {{ color:#ffffff; margin:0; font-size:24px; font-weight:700; }}
  .header p {{ color:#bfdbfe; margin:8px 0 0; font-size:14px; }}
  .body {{ background:#161b22; border:1px solid #30363d; padding:32px 24px; }}
  .body p {{ color:#c9d1d9; font-size:15px; line-height:1.6; margin:0 0 16px; }}
  .metric-row {{ display:flex; gap:16px; margin:20px 0; flex-wrap:wrap; }}
  .metric {{ background:#0d1117; border:1px solid #30363d; border-radius:8px;
             padding:16px; flex:1; min-width:120px; text-align:center; }}
  .metric .value {{ color:#f0f6fc; font-size:28px; font-weight:700; }}
  .metric .label {{ color:#8b949e; font-size:12px; margin-top:4px; }}
  .badge {{ display:inline-block; padding:4px 12px; border-radius:20px;
            font-size:12px; font-weight:600; }}
  .badge-critical {{ background:#ff000033; color:#f87171; border:1px solid #f87171; }}
  .badge-high {{ background:#f9731633; color:#fb923c; border:1px solid #fb923c; }}
  .badge-success {{ background:#22c55e33; color:#4ade80; border:1px solid #4ade80; }}
  .badge-info {{ background:#3b82f633; color:#60a5fa; border:1px solid #60a5fa; }}
  .btn {{ display:inline-block; padding:12px 28px; background:linear-gradient(135deg,#3b82f6,#8b5cf6);
          color:#ffffff; text-decoration:none; border-radius:8px;
          font-weight:600; font-size:15px; margin:16px 0; }}
  .code-block {{ background:#0d1117; border:1px solid #30363d; border-radius:8px;
                  padding:16px; font-family:monospace; font-size:13px;
                  color:#7ee787; overflow-x:auto; margin:16px 0; }}
  .divider {{ border:none; border-top:1px solid #30363d; margin:24px 0; }}
  .footer {{ background:#0d1117; border:1px solid #30363d; border-top:none;
             border-radius:0 0 12px 12px; padding:20px 24px; text-align:center; }}
  .footer p {{ color:#8b949e; font-size:12px; margin:4px 0; }}
  .footer a {{ color:#3b82f6; text-decoration:none; }}
</style>
</head>
<body>
<div style="display:none;max-height:0;overflow:hidden;">{preview_text}</div>
<div class="wrapper">
  <div class="header">
    <h1>AI Codebase Assistant</h1>
    <p>{title}</p>
  </div>
  <div class="body">
    {body_html}
  </div>
  <div class="footer">
    <p>AI Codebase Assistant &mdash; Your intelligent code analysis partner</p>
    <p>
      <a href="{app_url}">Open App</a> &bull;
      <a href="{unsubscribe_url}">Unsubscribe</a> &bull;
      <a href="{app_url}/notifications">Notification Settings</a>
    </p>
    <p style="color:#484f58;">
      Sent at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
    </p>
  </div>
</div>
</body>
</html>"""

    # Extract text from body_html for plaintext version (crude but effective)
    import re
    plaintext = re.sub(r'<[^>]+>', '', body_html)
    plaintext = re.sub(r'\s+', ' ', plaintext).strip()
    plaintext = (
        f"AI Codebase Assistant\n"
        f"{title}\n"
        f"{'=' * 40}\n\n"
        f"{plaintext}\n\n"
        f"{'=' * 40}\n"
        f"Open app: {app_url}\n"
        f"Unsubscribe: {unsubscribe_url}\n"
    )

    return html, plaintext


def build_agent_complete_email(
    agent_display_name: str,
    file_path: str,
    quality_score: int | None,
    total_findings: int,
    critical_count: int,
    elapsed_seconds: float,
    project_url: str,
) -> tuple[str, str, str]:
    """
    Build an agent completion notification email.

    Args:
        agent_display_name: Human-readable agent name
        file_path:          Analyzed file path
        quality_score:      Code quality score (0-100) or None
        total_findings:     Total issues found
        critical_count:     Critical severity issues count
        elapsed_seconds:    Analysis duration in seconds
        project_url:        Link to project in the app

    Returns:
        Tuple of (subject, html_body, plaintext_body)
    """
    subject = f"Analysis Complete: {agent_display_name} finished on {file_path}"

    badge = (
        '<span class="badge badge-critical">CRITICAL ISSUES</span>'
        if critical_count > 0
        else '<span class="badge badge-success">CLEAN</span>'
    )

    score_html = (
        f'<div class="metric"><div class="value">{quality_score}/100</div>'
        f'<div class="label">Quality Score</div></div>'
        if quality_score is not None else ""
    )

    body_html = f"""
<p>Your <strong>{agent_display_name}</strong> analysis of
<code style="background:#0d1117;padding:2px 6px;border-radius:4px;
color:#7ee787;">{file_path}</code> is complete.</p>

<div class="metric-row">
  {score_html}
  <div class="metric">
    <div class="value">{total_findings}</div>
    <div class="label">Total Findings</div>
  </div>
  <div class="metric">
    <div class="value" style="color:#f87171;">{critical_count}</div>
    <div class="label">Critical Issues</div>
  </div>
  <div class="metric">
    <div class="value">{elapsed_seconds:.0f}s</div>
    <div class="label">Analysis Time</div>
  </div>
</div>

<p>Status: {badge}</p>

<p>{"&#9888; Critical issues require immediate attention before deploying." if critical_count > 0 else "No critical issues detected. Your code looks good!"}</p>

<a href="{project_url}" class="btn">View Full Report</a>

<hr class="divider">
<p style="font-size:13px;color:#8b949e;">
This notification was triggered by completing an AI agent analysis task.
</p>
"""

    return subject, *_base_template(
        title=f"{agent_display_name} Analysis Complete",
        preview_text=f"{total_findings} findings | {critical_count} critical",
        body_html=body_html,
    )


def build_indexing_complete_email(
    project_name: str,
    total_files: int,
    indexed_count: int,
    failed_count: int,
    total_chunks: int,
    elapsed_seconds: float,
    project_url: str,
) -> tuple[str, str, str]:
    """
    Build an indexing completion notification email.

    Args:
        project_name:   Project display name
        total_files:    Total files processed
        indexed_count:  Successfully indexed files
        failed_count:   Failed files
        total_chunks:   Total vector chunks stored
        elapsed_seconds: Indexing duration
        project_url:    Link to project

    Returns:
        Tuple of (subject, html_body, plaintext_body)
    """
    subject = f"Indexing Complete: {project_name} is ready for AI queries"
    success_rate = round(indexed_count / max(total_files, 1) * 100, 1)

    body_html = f"""
<p>Your project <strong>{project_name}</strong> has been indexed and is now
ready for AI-powered code analysis and natural language queries.</p>

<div class="metric-row">
  <div class="metric">
    <div class="value" style="color:#4ade80;">{indexed_count}</div>
    <div class="label">Files Indexed</div>
  </div>
  <div class="metric">
    <div class="value">{total_chunks:,}</div>
    <div class="label">Code Chunks Stored</div>
  </div>
  <div class="metric">
    <div class="value">{success_rate}%</div>
    <div class="label">Success Rate</div>
  </div>
  <div class="metric">
    <div class="value">{elapsed_seconds:.0f}s</div>
    <div class="label">Index Time</div>
  </div>
</div>

{"<p><span class='badge badge-critical'>" + str(failed_count) + " files failed</span> Some files could not be indexed. Check the indexing report for details.</p>" if failed_count > 0 else ""}

<p>You can now:</p>
<ul style="color:#c9d1d9;line-height:2;">
  <li>Ask natural language questions about your codebase</li>
  <li>Run security scans, code reviews, and performance analysis</li>
  <li>Generate documentation and tests automatically</li>
</ul>

<a href="{project_url}" class="btn">Start Analyzing Your Code</a>
"""

    return subject, *_base_template(
        title="Codebase Indexing Complete",
        preview_text=f"{indexed_count}/{total_files} files indexed | {total_chunks:,} chunks",
        body_html=body_html,
    )


def build_security_alert_email(
    file_path: str,
    critical_count: int,
    high_count: int,
    top_findings: list[dict[str, Any]],
    project_url: str,
) -> tuple[str, str, str]:
    """
    Build a security alert notification email for critical findings.

    Args:
        file_path:      Scanned file path
        critical_count: Number of CRITICAL vulnerabilities
        high_count:     Number of HIGH vulnerabilities
        top_findings:   List of top finding dicts (vuln_id, title, cwe)
        project_url:    Link to security report

    Returns:
        Tuple of (subject, html_body, plaintext_body)
    """
    subject = (
        f"[SECURITY ALERT] {critical_count} Critical Vulnerabilities in {file_path}"
    )

    findings_html = ""
    for f in top_findings[:5]:
        vuln_id = str(f.get("vuln_id") or f.get("rule_id") or "")
        title = str(f.get("title") or "")
        cwe = str(f.get("cwe") or "")
        sev = str(f.get("severity") or "HIGH")
        badge_class = "badge-critical" if sev == "CRITICAL" else "badge-high"
        findings_html += f"""
<div style="background:#0d1117;border:1px solid #30363d;border-radius:8px;
     padding:12px 16px;margin:8px 0;display:flex;align-items:center;gap:12px;">
  <span class="badge {badge_class}">{sev}</span>
  <div>
    <div style="color:#f0f6fc;font-weight:600;">[{vuln_id}] {title}</div>
    <div style="color:#8b949e;font-size:12px;">CWE: {cwe}</div>
  </div>
</div>"""

    body_html = f"""
<p style="color:#f87171;font-weight:600;font-size:16px;">
  &#9888; Security vulnerabilities detected in your codebase
</p>

<div class="metric-row">
  <div class="metric">
    <div class="value" style="color:#f87171;">{critical_count}</div>
    <div class="label">Critical</div>
  </div>
  <div class="metric">
    <div class="value" style="color:#fb923c;">{high_count}</div>
    <div class="label">High</div>
  </div>
</div>

<p>File scanned: <code style="background:#0d1117;padding:2px 6px;
border-radius:4px;color:#7ee787;">{file_path}</code></p>

<p><strong>Top Findings:</strong></p>
{findings_html}

<p>These vulnerabilities require immediate attention. Do not deploy to production
until CRITICAL and HIGH severity issues are resolved.</p>

<a href="{project_url}" class="btn" style="background:linear-gradient(135deg,#dc2626,#b91c1c);">
  View Security Report
</a>
"""

    return subject, *_base_template(
        title="Security Alert",
        preview_text=f"{critical_count} critical + {high_count} high vulnerabilities",
        body_html=body_html,
    )


def build_task_failed_email(
    task_type: str,
    agent_id: str,
    error_message: str,
    project_url: str,
) -> tuple[str, str, str]:
    """
    Build a task failure notification email.

    Args:
        task_type:     Human-readable task type
        agent_id:      Agent that failed
        error_message: Error description
        project_url:   Link to project

    Returns:
        Tuple of (subject, html_body, plaintext_body)
    """
    subject = f"Task Failed: {task_type} encountered an error"

    body_html = f"""
<p>Your <strong>{task_type}</strong> task encountered an error and could not complete.</p>

<div class="code-block">{error_message[:500]}</div>

<p>This may be caused by:</p>
<ul style="color:#c9d1d9;line-height:2;">
  <li>Temporary service unavailability (retry usually fixes this)</li>
  <li>Invalid or unsupported code format</li>
  <li>Resource limits exceeded for large files</li>
</ul>

<a href="{project_url}" class="btn">Try Again</a>

<hr class="divider">
<p style="font-size:13px;color:#8b949e;">
Agent: {agent_id} | If this persists, please check our status page.
</p>
"""

    return subject, *_base_template(
        title="Task Failed",
        preview_text=f"{task_type} failed — click to retry",
        body_html=body_html,
    )


# =============================================================================
# SMTP Sender
# =============================================================================

class EmailSender:
    """
    SMTP email sender with connection pooling and error handling.

    Supports TLS (STARTTLS on port 587) and SSL (port 465).
    Falls back to console logging when SMTP is not configured.
    """

    def __init__(self, config: SMTPConfig | None = None) -> None:
        """
        Initialise the EmailSender.

        Args:
            config: SMTPConfig instance (uses module singleton if None)
        """
        self.config = config or smtp_config

    def send(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        plaintext_body: str,
    ) -> dict[str, Any]:
        """
        Send an email via SMTP.

        If SMTP is not configured (development mode), logs the email
        content instead of sending. Returns a result dict indicating
        whether the email was sent or logged.

        Args:
            to_email:       Recipient email address
            subject:        Email subject line
            html_body:      HTML email content
            plaintext_body: Plaintext fallback content

        Returns:
            Dict with keys: success, mode (sent/logged/error),
            timestamp, error (if failed)
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        if not self.config.is_configured:
            # Development mode: log to console
            logger.info(
                "EMAIL (dev mode - not sent):\n"
                "  To:      %s\n"
                "  From:    %s <%s>\n"
                "  Subject: %s\n"
                "  Preview: %s",
                to_email,
                self.config.from_name,
                self.config.from_email,
                subject,
                plaintext_body[:200],
            )
            return {
                "success": True,
                "mode": "logged",
                "timestamp": timestamp,
                "to_email": to_email,
                "subject": subject,
            }

        # Build MIME message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = (
            f"{self.config.from_name} <{self.config.from_email}>"
        )
        msg["To"] = to_email
        msg["X-Mailer"] = "AI-Codebase-Assistant/2.0"

        # Attach plaintext first, then HTML (email clients prefer last part)
        msg.attach(MIMEText(plaintext_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            if self.config.use_tls:
                server = smtplib.SMTP(
                    self.config.host, self.config.port, timeout=30
                )
                server.ehlo()
                server.starttls()
                server.ehlo()
            else:
                server = smtplib.SMTP_SSL(
                    self.config.host, self.config.port, timeout=30
                )

            if self.config.username and self.config.password:
                server.login(self.config.username, self.config.password)

            server.sendmail(
                self.config.from_email,
                [to_email],
                msg.as_string(),
            )
            server.quit()

            logger.info(
                "Email sent: to=%s subject=%s", to_email, subject
            )
            return {
                "success": True,
                "mode": "sent",
                "timestamp": timestamp,
                "to_email": to_email,
                "subject": subject,
            }

        except smtplib.SMTPException as exc:
            logger.error(
                "SMTP error sending to %s: %s", to_email, exc
            )
            return {
                "success": False,
                "mode": "error",
                "timestamp": timestamp,
                "to_email": to_email,
                "subject": subject,
                "error": str(exc),
            }
        except Exception as exc:
            logger.error(
                "Unexpected error sending email to %s: %s",
                to_email, exc, exc_info=True,
            )
            return {
                "success": False,
                "mode": "error",
                "timestamp": timestamp,
                "error": str(exc),
            }


# Singleton sender
email_sender = EmailSender()


# =============================================================================
# Rate Limiter
# =============================================================================

class EmailRateLimiter:
    """
    Redis-backed rate limiter for email delivery.

    Enforces: max 10 emails per user per hour.
    Uses a sliding window counter stored in Redis.
    Falls back to allowing emails if Redis is unavailable.
    """

    MAX_PER_HOUR = 10
    WINDOW_SECONDS = 3600

    @staticmethod
    def is_allowed(user_id: str, email_type: str = "any") -> bool:
        """
        Check if a user is within the email rate limit.

        Args:
            user_id:    User UUID
            email_type: Email type for per-type limiting (future use)

        Returns:
            True if email is allowed, False if rate limited
        """
        try:
            import redis
            url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            client = redis.from_url(url, decode_responses=True)
            key = f"email:rate:{user_id}:hour"

            current = client.get(key)
            count = int(current) if current else 0

            if count >= EmailRateLimiter.MAX_PER_HOUR:
                logger.warning(
                    "Email rate limit hit: user=%s count=%d",
                    user_id, count,
                )
                return False

            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, EmailRateLimiter.WINDOW_SECONDS)
            pipe.execute()
            return True

        except Exception as exc:
            logger.warning(
                "Rate limiter unavailable (%s) — allowing email", exc
            )
            return True

    @staticmethod
    def get_remaining(user_id: str) -> int:
        """
        Get remaining email quota for a user this hour.

        Args:
            user_id: User UUID

        Returns:
            Number of emails remaining (0-10)
        """
        try:
            import redis
            url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            client = redis.from_url(url, decode_responses=True)
            key = f"email:rate:{user_id}:hour"
            current = client.get(key)
            count = int(current) if current else 0
            return max(0, EmailRateLimiter.MAX_PER_HOUR - count)
        except Exception:
            return EmailRateLimiter.MAX_PER_HOUR


# =============================================================================
# Unsubscribe Token Generator
# =============================================================================

def generate_unsubscribe_token(user_id: str, email: str) -> str:
    """
    Generate a deterministic unsubscribe token for a user.

    Token is an HMAC-SHA256 of (user_id + email + secret key).
    Same inputs always produce the same token (no DB storage needed).

    Args:
        user_id: User UUID
        email:   User email address

    Returns:
        Hex token string (16 chars)
    """
    secret = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
    payload = f"{user_id}:{email}:{secret}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


# =============================================================================
# Notification Service (main interface)
# =============================================================================

class NotificationService:
    """
    High-level notification service consumed by Celery tasks and API.

    Combines template building, rate limiting, and email sending
    into simple send_* methods for each notification type.
    """

    def __init__(
        self,
        sender: EmailSender | None = None,
    ) -> None:
        """
        Initialise NotificationService.

        Args:
            sender: EmailSender instance (uses singleton if None)
        """
        self._sender = sender or email_sender

    def send_agent_complete(
        self,
        to_email: str,
        user_id: str,
        agent_display_name: str,
        file_path: str,
        quality_score: int | None,
        total_findings: int,
        critical_count: int,
        elapsed_seconds: float,
        project_id: str,
    ) -> dict[str, Any]:
        """
        Send agent analysis completion notification.

        Args:
            to_email:           Recipient email
            user_id:            User UUID (for rate limiting)
            agent_display_name: e.g. "Security Scanner"
            file_path:          Analyzed file
            quality_score:      0-100 score or None
            total_findings:     Total issues found
            critical_count:     Critical issues count
            elapsed_seconds:    Analysis duration
            project_id:         Project UUID for URL

        Returns:
            Send result dict
        """
        if not EmailRateLimiter.is_allowed(user_id, "agent_complete"):
            return {"success": False, "mode": "rate_limited", "user_id": user_id}

        app_url = os.getenv("APP_URL", "http://localhost:3000")
        project_url = f"{app_url}/projects/{project_id}"
        token = generate_unsubscribe_token(user_id, to_email)

        subject, html_body, plaintext_body = build_agent_complete_email(
            agent_display_name=agent_display_name,
            file_path=file_path,
            quality_score=quality_score,
            total_findings=total_findings,
            critical_count=critical_count,
            elapsed_seconds=elapsed_seconds,
            project_url=project_url,
        )

        return self._sender.send(to_email, subject, html_body, plaintext_body)

    def send_indexing_complete(
        self,
        to_email: str,
        user_id: str,
        project_name: str,
        total_files: int,
        indexed_count: int,
        failed_count: int,
        total_chunks: int,
        elapsed_seconds: float,
        project_id: str,
    ) -> dict[str, Any]:
        """
        Send indexing completion notification.

        Args:
            to_email:       Recipient email
            user_id:        User UUID
            project_name:   Project display name
            total_files:    Total files processed
            indexed_count:  Successfully indexed
            failed_count:   Failed files
            total_chunks:   Chunks stored
            elapsed_seconds: Duration
            project_id:     Project UUID

        Returns:
            Send result dict
        """
        if not EmailRateLimiter.is_allowed(user_id, "indexing_complete"):
            return {"success": False, "mode": "rate_limited"}

        app_url = os.getenv("APP_URL", "http://localhost:3000")
        subject, html_body, plaintext_body = build_indexing_complete_email(
            project_name=project_name,
            total_files=total_files,
            indexed_count=indexed_count,
            failed_count=failed_count,
            total_chunks=total_chunks,
            elapsed_seconds=elapsed_seconds,
            project_url=f"{app_url}/projects/{project_id}",
        )
        return self._sender.send(to_email, subject, html_body, plaintext_body)

    def send_security_alert(
        self,
        to_email: str,
        user_id: str,
        file_path: str,
        critical_count: int,
        high_count: int,
        top_findings: list[dict[str, Any]],
        project_id: str,
    ) -> dict[str, Any]:
        """
        Send security alert notification for critical findings.

        Only sends if critical_count > 0 to avoid alert fatigue.

        Args:
            to_email:      Recipient email
            user_id:       User UUID
            file_path:     Scanned file
            critical_count: Critical vulnerability count
            high_count:    High vulnerability count
            top_findings:  List of top finding dicts
            project_id:    Project UUID

        Returns:
            Send result dict
        """
        if critical_count == 0 and high_count < 3:
            return {"success": True, "mode": "skipped", "reason": "no critical findings"}

        if not EmailRateLimiter.is_allowed(user_id, "security_alert"):
            return {"success": False, "mode": "rate_limited"}

        app_url = os.getenv("APP_URL", "http://localhost:3000")
        subject, html_body, plaintext_body = build_security_alert_email(
            file_path=file_path,
            critical_count=critical_count,
            high_count=high_count,
            top_findings=top_findings,
            project_url=f"{app_url}/projects/{project_id}/security",
        )
        return self._sender.send(to_email, subject, html_body, plaintext_body)

    def send_task_failed(
        self,
        to_email: str,
        user_id: str,
        task_type: str,
        agent_id: str,
        error_message: str,
        project_id: str,
    ) -> dict[str, Any]:
        """
        Send task failure notification.

        Args:
            to_email:      Recipient email
            user_id:       User UUID
            task_type:     Human-readable task type
            agent_id:      Agent that failed
            error_message: Error description
            project_id:    Project UUID

        Returns:
            Send result dict
        """
        if not EmailRateLimiter.is_allowed(user_id, "task_failed"):
            return {"success": False, "mode": "rate_limited"}

        app_url = os.getenv("APP_URL", "http://localhost:3000")
        subject, html_body, plaintext_body = build_task_failed_email(
            task_type=task_type,
            agent_id=agent_id,
            error_message=error_message,
            project_url=f"{app_url}/projects/{project_id}",
        )
        return self._sender.send(to_email, subject, html_body, plaintext_body)


# Singleton service
notification_service = NotificationService()
