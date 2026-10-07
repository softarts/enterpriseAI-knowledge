"""Tests for configuration module."""

import importlib
import os
import unittest
from unittest.mock import patch, MagicMock


class TestConfig(unittest.TestCase):
    """Test configuration module."""
    
    def test_default_user_id(self):
        """Test default user ID is 1234."""
        with patch('sys.argv', ['app.py']):
            from app.config import get_user_id, DEFAULT_USER_ID
            user_id = get_user_id()
            self.assertEqual(user_id, DEFAULT_USER_ID)
    
    def test_custom_user_id(self):
        """Test custom user ID from command line."""
        with patch('sys.argv', ['app.py', '--user-id', '9999']):
            # Need to reimport to get fresh argparse
            import importlib
            import app.config
            importlib.reload(app.config)
            user_id = app.config.get_user_id()
            self.assertEqual(user_id, "9999")
    
    def test_missing_env_vars_raises_error(self):
        """Test missing environment variables raise ValueError."""
        # Clear env vars
        env_vars = ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"]
        old_values = {var: os.environ.get(var) for var in env_vars}
        
        try:
            for var in env_vars:
                if var in os.environ:
                    del os.environ[var]
            
            # Force reimport to pick up env changes
            import app.config
            importlib.reload(app.config)
            
            with self.assertRaises(ValueError) as ctx:
                app.config.get_llm_config()
            
            self.assertIn("Missing required environment variables", str(ctx.exception))
            
        finally:
            # Restore env vars
            for var, value in old_values.items():
                if value is not None:
                    os.environ[var] = value
    
    def test_get_llm_config_returns_dict(self):
        """Test get_llm_config returns expected dict structure."""
        os.environ["LLM_API_KEY"] = "test-key"
        os.environ["LLM_BASE_URL"] = "https://api.test.com"
        os.environ["LLM_MODEL"] = "test-model"
        
        try:
            from app.config import get_llm_config
            config = get_llm_config()
            
            self.assertIn("api_key", config)
            self.assertIn("base_url", config)
            self.assertIn("model", config)
            self.assertEqual(config["api_key"], "test-key")
            self.assertEqual(config["base_url"], "https://api.test.com")
            self.assertEqual(config["model"], "test-model")
            
        finally:
            del os.environ["LLM_API_KEY"]
            del os.environ["LLM_BASE_URL"]
            del os.environ["LLM_MODEL"]
    
    def test_log_dir_creation(self):
        """Test log directory is created."""
        from app.config import get_log_dir
        log_dir = get_log_dir()
        self.assertTrue(log_dir.exists())
        self.assertTrue(log_dir.is_dir())


if __name__ == "__main__":
    unittest.main()