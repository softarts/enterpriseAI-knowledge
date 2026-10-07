"""Trace ID generation utilities."""

from typing import Any

import uuid


def generate_trace_id() -> str:
    """Generate a unique trace ID for each conversation turn."""
    return str(uuid.uuid4())


def sanitize_for_json(obj: Any) -> Any:
    """Sanitize an object for JSON serialization."""
    # Check callable first because functions have __dict__ but we want to capture them
    if callable(obj):
        return f"<callable: {obj.__name__}>"
    elif hasattr(obj, '__dict__'):
        return sanitize_for_json(obj.__dict__)
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, bytes):
        return f"<bytes: {len(obj)} bytes>"
    else:
        return obj