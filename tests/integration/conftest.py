"""
Integration test configuration.

These tests run against the real ice9 API and require:
  - ICE9_API_KEY  — a valid API key
  - ICE9_BASE_URL — API base URL (defaults to https://api.ice9.ai)

Optional local image overrides:
  - ICE9_TEST_IMAGE        — real image used for live integration tests
  - ICE9_BASIC_TEST_IMAGE  — real image used specifically for basic-tier tests

Run them explicitly:

    pytest tests/integration/ -v

They are excluded from the default test run.
"""
import os
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_REAL_TEST_IMAGE = _REPO_ROOT / "images" / "z-test.jpg"


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
    """A path-based image for live integration tests.

    Prefer a real local fixture when available so content-aware services
    like pose/face/grounding are exercised with realistic input. Fall back
    to a synthetic JPEG only when no local test image is configured.
    """
    configured = os.environ.get("ICE9_TEST_IMAGE")
    for candidate in (configured, str(_DEFAULT_REAL_TEST_IMAGE)):
        if candidate and Path(candidate).is_file():
            return Path(candidate)

    from PIL import Image
    path = tmp_path_factory.mktemp("images") / "test.jpg"
    Image.new("RGB", (64, 64), color=(128, 128, 128)).save(path, format="JPEG")
    return path


@pytest.fixture(scope="module")
def basic_test_image(test_image):
    """A real-image fixture for basic-tier live tests when available."""
    configured = os.environ.get("ICE9_BASIC_TEST_IMAGE") or os.environ.get("ICE9_TEST_IMAGE")
    for candidate in (configured, str(_DEFAULT_REAL_TEST_IMAGE)):
        if candidate and Path(candidate).is_file():
            return Path(candidate)

    pytest.skip(
        "Basic-tier live integration requires a real image fixture. "
        "Set ICE9_BASIC_TEST_IMAGE or place a local fixture at images/z-test.jpg."
    )
