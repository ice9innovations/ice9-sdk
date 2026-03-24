"""
Integration test configuration.

These tests run against the real ice9 API and require:
  - ICE9_API_KEY  — a valid API key
  - ICE9_BASE_URL — API base URL (defaults to https://api.ice9.ai)

Run them explicitly:

    pytest tests/integration/ -v

They are excluded from the default test run.
"""
import os
import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: mark test as requiring a live API connection"
    )


def _require_env(*names):
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    pytest.skip(f"None of {', '.join(names)} environment variables are set")


@pytest.fixture(scope="session")
def api_key():
    return _require_env("ICE9_API_KEY", "API_KEY")


@pytest.fixture(scope="session")
def base_url():
    return os.environ.get("ICE9_BASE_URL") or os.environ.get("API_URL") or "https://api.ice9.ai"


@pytest.fixture(scope="session")
def client(api_key, base_url):
    from ice9 import Ice9
    return Ice9(api_key=api_key, base_url=base_url)


@pytest.fixture(scope="module")
def test_image(tmp_path_factory):
    """A small valid JPEG on disk. Path-based so it can be submitted multiple times."""
    from PIL import Image
    path = tmp_path_factory.mktemp("images") / "test.jpg"
    Image.new("RGB", (64, 64), color=(128, 128, 128)).save(path, format="JPEG")
    return path
