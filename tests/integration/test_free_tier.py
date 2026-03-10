"""
Integration tests — free tier.

Verifies that the SDK works end-to-end against the real API using a free-tier
key. All five free-tier services (nudenet, colors, metadata, ocr, qr) should
complete within a few seconds.

Run with:
    ICE9_API_KEY=ice9_... pytest tests/integration/test_free_tier.py -v
"""
import pytest

from ice9 import Ice9, AnalysisResult
from ice9.exceptions import PartialResultError


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def free_result(client, test_image):
    """One completed free-tier analysis, shared across all tests in this module."""
    return client.analyze(test_image, tier="free")


@pytest.fixture(scope="module")
def free_tiers(client):
    """Tier config, fetched once for the module."""
    return client.tiers()


# ---------------------------------------------------------------------------
# Tiers endpoint

def test_tiers_endpoint_includes_free(free_tiers):
    assert "free" in free_tiers
    assert isinstance(free_tiers["free"], list)
    assert len(free_tiers["free"]) > 0


# ---------------------------------------------------------------------------
# Analysis result

def test_analyze_returns_result(free_result):
    assert isinstance(free_result, AnalysisResult)
    assert free_result.image_id > 0


def test_analyze_free_tier_is_complete(free_result):
    assert free_result.services_failed == {}


def test_analyze_nudenet_is_present(free_result):
    assert free_result.nudenet is not None


def test_all_submitted_services_have_results(free_result):
    for service in free_result.services_submitted:
        assert getattr(free_result, service) is not None, f"Missing result for service: {service}"


def test_analyze_services_match_tier_config(free_result, free_tiers):
    assert set(free_result.services_submitted) == set(free_tiers["free"])


# ---------------------------------------------------------------------------
# image_group — needs its own submission since it uses a different group tag

def test_analyze_image_group_is_set(client, test_image):
    result = client.analyze(test_image, tier="free", image_group="sdk-integration-test")
    assert result._raw.get("image_group") == "sdk-integration-test"
