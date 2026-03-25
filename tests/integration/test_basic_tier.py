"""
Integration tests — basic tier.

Verifies that the SDK works end-to-end for the basic tier, which includes
VLM services (blip, florence2, moondream, ollama, qwen) in addition to the
fast services present in free. VLMs take longer, so a higher timeout is used.

Run with:
    ICE9_API_KEY=ice9_... pytest tests/integration/test_basic_tier.py -v
"""
import pytest

from ice9 import Ice9, AnalysisResult
from ice9.exceptions import PartialResultError


pytestmark = pytest.mark.integration

# Basic tier now includes enough downstream work that live API completion can
# exceed two minutes under load. Keep the integration timeout comfortably above
# observed production latency so release gating reflects correctness, not queueing.
BASIC_TIMEOUT = 240.0


@pytest.fixture(scope="module")
def basic_client(api_key, base_url):
    """Client with a timeout appropriate for VLM workloads."""
    return Ice9(api_key=api_key, base_url=base_url, timeout=BASIC_TIMEOUT)


@pytest.fixture(scope="module")
def basic_result(basic_client, test_image):
    """One completed basic-tier analysis, shared across all tests in this module."""
    return basic_client.analyze(test_image, tier="basic", raise_on_partial=False)


@pytest.fixture(scope="module")
def basic_tiers(basic_client):
    return basic_client.tiers()


# ---------------------------------------------------------------------------
# Tier config

def test_tiers_endpoint_includes_basic(basic_tiers):
    assert "basic" in basic_tiers
    assert len(basic_tiers["basic"]) > len(basic_tiers["free"])


def test_basic_tier_includes_free_tier_services(basic_tiers):
    free = set(basic_tiers["free"])
    basic = set(basic_tiers["basic"])
    assert free.issubset(basic), f"Basic tier missing free-tier services: {free - basic}"


# ---------------------------------------------------------------------------
# Analysis result

def test_analyze_returns_result(basic_result):
    assert isinstance(basic_result, AnalysisResult)
    assert basic_result.image_id > 0


def test_analyze_basic_tier_only_allows_known_backend_failures(basic_result):
    assert set(basic_result.services_failed).issubset({"pose"})


def test_analyze_nudenet_is_present(basic_result):
    assert basic_result.nudenet is not None


def test_all_submitted_services_have_results(basic_result):
    for service in basic_result.services_submitted:
        if service in basic_result.services_failed:
            continue
        assert getattr(basic_result, service) is not None, f"Missing result for service: {service}"


def test_analyze_services_match_tier_config(basic_result, basic_tiers):
    assert set(basic_result.services_submitted) == set(basic_tiers["basic"])


def test_basic_has_more_results_than_free(basic_result, basic_tiers):
    assert len(basic_result.services_submitted) > len(basic_tiers["free"])
