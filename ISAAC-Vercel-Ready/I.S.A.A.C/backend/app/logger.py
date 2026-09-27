"""
Structured and sanitized logging configuration for ISAAC backend.
Enforces automatic redaction of credentials, passwords, tokens, and secrets (Phase 17).
"""

import logging
import re
import sys
from typing import Any


class SensitiveDataMaskingFilter(logging.Filter):
    """
    Log filter that intercepts and masks sensitive data patterns:
    - Passwords, secret keys, API tokens
    - Bearer authorization tokens
    - Database connection strings with embedded credentials
    """

    PATTERNS = [
        # Passwords in JSON / dict / query format
        (re.compile(r'(["\']?password["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1[REDACTED]\3'),
        (re.compile(r'(["\']?secret["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1[REDACTED]\3'),
        (re.compile(r'(["\']?token["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1[REDACTED]\3'),
        # Bearer tokens in headers or logs
        (re.compile(r'(Bearer\s+)[a-zA-Z0-9_\-\.]{10,}', re.IGNORECASE), r'\1[REDACTED_BEARER_TOKEN]'),
        # Database connection strings with passwords: mysql+pymysql://user:password@host:port/db
        (re.compile(r'(://[^:]+:)([^@]+)(@)', re.IGNORECASE), r'\1[REDACTED]\3'),
        # Authorization header lines
        (re.compile(r'(Authorization:\s*)[^\r\n]+', re.IGNORECASE), r'\1[REDACTED]'),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.mask_sensitive_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self.mask_sensitive_text(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self.mask_sensitive_text(str(a)) for a in record.args)
        return True

    @classmethod
    def mask_sensitive_text(cls, text: str) -> str:
        """Apply all redaction regex patterns to sanitize input string."""
        if not isinstance(text, str):
            return text
        sanitized = text
        for pattern, replacement in cls.PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized


def setup_logger(name: str = "isaac") -> logging.Logger:
    """Configure and return an application logger with security redaction filter."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        handler.addFilter(SensitiveDataMaskingFilter())
        logger.addHandler(handler)
        logger.addFilter(SensitiveDataMaskingFilter())
    return logger


logger = setup_logger()
