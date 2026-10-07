"""Tests for trace and logging functionality."""

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile


class TestTraceId(unittest.TestCase):
    """Test trace ID generation."""
    
    def test_generate_trace_id(self):
        """Test trace ID is generated and unique."""
        from app.trace import generate_trace_id
        
        trace_id_1 = generate_trace_id()
        trace_id_2 = generate_trace_id()
        
        # Should be valid UUID
        self.assertTrue(len(trace_id_1) == 36)  # UUID format
        self.assertIn("-", trace_id_1)
        
        # Should be unique
        self.assertNotEqual(trace_id_1, trace_id_2)
    
    def test_sanitize_for_json(self):
        """Test JSON sanitization."""
        from app.trace import sanitize_for_json
        
        # Test dict
        obj = {"key": "value"}
        self.assertEqual(sanitize_for_json(obj), obj)
        
        # Test bytes
        obj = b"hello"
        result = sanitize_for_json(obj)
        self.assertIn("bytes", result)
        
        # Test callable
        def foo():
            pass
        result = sanitize_for_json(foo)
        self.assertIn("callable", result)


class TestRedaction(unittest.TestCase):
    """Test sensitive data redaction."""
    
    def test_redact_api_key_header(self):
        """Test API key is redacted in headers."""
        from app.utils.redaction import redact_headers
        
        headers = {
            "Authorization": "Bearer sk-1234567890",
            "Content-Type": "application/json"
        }
        
        redacted = redact_headers(headers)
        
        self.assertIn("AUTHORIZATION_REDACTED", redacted["Authorization"])
        self.assertEqual(redacted["Content-Type"], "application/json")
    
    def test_redact_api_key_payload(self):
        """Test API key is redacted in JSON payload."""
        from app.utils.redaction import redact_json_payload
        
        payload = {
            "model": "gpt-4",
            "api_key": "sk-secret123"
        }
        
        redacted = redact_json_payload(payload)
        
        self.assertEqual(redacted["model"], "gpt-4")
        self.assertIn("REDACTED", redacted["api_key"])
    
    def test_redact_cookie_header(self):
        """Test cookie is redacted."""
        from app.utils.redaction import redact_headers
        
        headers = {
            "Cookie": "session=abc123; token=xyz789"
        }
        
        redacted = redact_headers(headers)
        
        self.assertIn("REDACTED", redacted["Cookie"])


class TestJsonLinesLogging(unittest.TestCase):
    """Test JSON Lines logging format."""
    
    def setUp(self):
        """Set up test environment."""
        # Create temp log file
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = Path(self.temp_dir) / "test.jsonl"
    
    def tearDown(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_json_lines_format(self):
        """Test log entries are valid JSON Lines."""
        from app.logging_config import JsonLinesHandler
        import logging
        
        # Create handler
        handler = JsonLinesHandler(self.log_file)
        
        # Create logger
        logger = logging.getLogger("test_json_lines")
        logger.setLevel(logging.DEBUG)
        logger.handlers = []
        logger.addHandler(handler)
        
        # Log an entry
        extra = {
            "trace_id": "test-trace-123",
            "event_type": "test_event",
            "component": "test",
            "payload": {"key": "value"}
        }
        
        logger.info("Test message", extra=extra)
        
        # Read and verify
        with open(self.log_file, "r") as f:
            line = f.readline()
            entry = json.loads(line)
        
        # Check required fields
        self.assertIn("timestamp", entry)
        self.assertIn("trace_id", entry)
        self.assertIn("event_type", entry)
        self.assertIn("component", entry)
        self.assertIn("sequence", entry)
        self.assertIn("payload", entry)
        
        # Check trace_id
        self.assertEqual(entry["trace_id"], "test-trace-123")
        self.assertEqual(entry["event_type"], "test_event")


if __name__ == "__main__":
    unittest.main()