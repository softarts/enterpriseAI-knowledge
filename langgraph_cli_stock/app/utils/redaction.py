"""Redaction utilities for sensitive information in logs."""

import re
from typing import Any, Dict


# Patterns that indicate sensitive data
SENSITIVE_HEADERS = {
    "authorization",
    "api-key",
    "apikey",
    "x-api-key",
    "cookie",
    "set-cookie",
    "x-auth-token",
    "bearer",
}

SENSITIVE_KEYS = {
    "api_key",
    "api-key",
    "apikey",
    "apiKey",
    "secret",
    "password",
    "token",
    "access_token",
    "access-token",
    "authorization",
    "auth",
}


def redact_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Redact sensitive information from HTTP headers."""
    redacted = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADERS:
            redacted[key] = f"<{key.upper()}_REDACTED>"
        else:
            redacted[key] = value
    return redacted


def redact_json_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Redact sensitive information from JSON payload."""
    if not isinstance(payload, dict):
        return payload
    
    redacted = {}
    for key, value in payload.items():
        key_lower = key.lower()
        if key_lower in SENSITIVE_KEYS:
            redacted[key] = f"<{key_upper}_REDACTED>" if (key_upper := key.upper()) else "<REDACTED>"
        elif isinstance(value, dict):
            redacted[key] = redact_json_payload(value)
        elif isinstance(value, str) and len(value) > 500:
            # Truncate long strings but don't redact unless explicitly sensitive
            redacted[key] = value[:500] + "..."
        else:
            redacted[key] = value
    
    return redacted


def redact_value(value: str, field_name: str = "") -> str:
    """Redact a specific value based on field name."""
    field_lower = field_name.lower()
    
    if field_lower in SENSITIVE_KEYS:
        return f"<{field_upper}_REDACTED>" if (field_upper := field_name.upper()) else "<REDACTED>"
    
    # Check if value looks like an API key (starts with sk-)
    if isinstance(value, str) and value.startswith("sk-"):
        return f"sk-{'*' * 20}"
    
    return value