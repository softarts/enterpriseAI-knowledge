"""Shared test fixtures."""

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def set_test_okf_dir(monkeypatch):
    """Point KB_OKF_DIR to the test fixtures directory."""
    fixtures_dir = str(Path(__file__).parent / "fixtures" / "okf")
    monkeypatch.setenv("KB_OKF_DIR", fixtures_dir)

    # Reset the settings singleton so it picks up the new env var
    import doc_service.core.config as config_module
    from doc_service.core.config import Settings

    config_module.settings = Settings()

    # Reset the service singleton so it recreates with new settings
    from doc_service.api.dependencies import reset_service

    reset_service()

    yield

    # Cleanup after test
    reset_service()


@pytest.fixture
def client(set_test_okf_dir):
    """Create a test client for the FastAPI app."""
    from doc_service.main import app
    from starlette.testclient import TestClient

    return TestClient(app)


@pytest.fixture
def fixtures_dir():
    """Return the path to the test fixtures OKF directory."""
    return Path(__file__).parent / "fixtures" / "okf"
