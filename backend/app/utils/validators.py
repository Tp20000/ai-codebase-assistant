"""
Input Validators — Reusable Pydantic validators and standalone validation functions.
Used across all API schemas to enforce data integrity at the boundary.
"""

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Regex patterns
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{3,30}$")


def validate_email(email: str) -> str:
    """
    Validate email format using RFC 5322 simplified regex.

    Args:
        email: Email string to validate

    Returns:
        Lowercase stripped email if valid

    Raises:
        ValueError: If email format is invalid
    """
    email = email.strip().lower()
    if not EMAIL_REGEX.match(email):
        raise ValueError(f"'{email}' is not a valid email address.")
    return email


def validate_username(username: str) -> str:
    """
    Validate username format.
    Rules: 3-30 chars, alphanumeric + underscores + hyphens only.

    Args:
        username: Username string to validate

    Returns:
        Stripped username if valid

    Raises:
        ValueError: If username does not meet requirements
    """
    username = username.strip()
    if not USERNAME_REGEX.match(username):
        raise ValueError(
            "Username must be 3-30 characters and contain only "
            "letters, numbers, underscores, or hyphens."
        )
    return username


def sanitize_string(value: str, max_length: int = 255) -> str:
    """
    Strip whitespace and enforce max length on a string.

    Args:
        value: Input string
        max_length: Maximum allowed length (default 255)

    Returns:
        Sanitized string

    Raises:
        ValueError: If value exceeds max_length after stripping
    """
    value = value.strip()
    if len(value) > max_length:
        raise ValueError(f"Value exceeds maximum length of {max_length} characters.")
    return value
