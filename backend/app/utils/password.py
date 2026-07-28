"""
Password Utilities — bcrypt hashing compatible with bcrypt 4.x and 5.x
"""

import logging
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

# Use bcrypt with explicit configuration
# bcrypt 4.x changed the API — this config works with both 4.x and 5.x
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
    bcrypt__ident="2b",
)


def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password using bcrypt.
    
    Args:
        plain_password: The user plain-text password
        
    Returns:
        bcrypt hash string
    """
    if not plain_password:
        raise ValueError("Password cannot be empty.")
    try:
        return pwd_context.hash(plain_password)
    except Exception as exc:
        logger.error(f"Password hashing failed: {exc}")
        raise


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify plain-text password against bcrypt hash.
    Uses constant-time comparison to prevent timing attacks.
    
    Args:
        plain_password: Input password
        hashed_password: Stored bcrypt hash
        
    Returns:
        True if password matches
    """
    if not plain_password or not hashed_password:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as exc:
        logger.warning(f"Password verification error: {exc}")
        return False


def is_password_strong(password: str) -> tuple[bool, str]:
    """
    Validate password strength.
    
    Rules:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter  
    - At least one digit
    - At least one special character
    
    Returns:
        Tuple of (is_valid, reason_if_invalid)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number."
    special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    if not any(c in special_chars for c in password):
        return False, f"Password must contain at least one special character."
    return True, ""
