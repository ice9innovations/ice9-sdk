"""
Integration tests — basic tier.

Verifies that the SDK works end-to-end for the basic tier, which includes
moderation, content analysis, metadata, colors, and object detection.

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
def basic_result(basic_client, basic_test_image):
    """One completed basic-tier analysis, shared across all tests in this module."""
    return basic_client.analyze(basic_test_image, tier="basic", raise_on_partial=False)


@pytest.fixture(scope="module")
def basic_tiers(basic_client):
    return basic_client.tiers()


# ---------------------------------------------------------------------------
# Tier config

def test_tiers_endpoint_includes_basic(basic_tiers):
    assert "basic" in basic_tiers
    assert set(basic_tiers) == {"basic", "cloud", "extra", "premium"}


def test_basic_tier_includes_baseline_services(basic_tiers):
    basic = set(basic_tiers["basic"])
    expected = {"colors", "content_analysis", "metadata", "nsfw2", "nudenet", "yolo_v8"}
    assert expected.issubset(basic), f"Basic tier missing services: {expected - basic}"


# ---------------------------------------------------------------------------
# Analysis result

def test_analyze_returns_result(basic_result):
    assert isinstance(basic_result, AnalysisResult)
    assert basic_result.image_id > 0


def test_analyze_basic_tier_only_allows_known_backend_failures(basic_result):
    assert set(basic_result.services_failed).issubset({"pose"})


def test_analyze_nudenet_is_present(basic_result):
    assert basic_result.nudenet is not None


def test_basic_tier_inherits_nsfw_helpers(basic_result):
    assert isinstance(basic_result.nsfw_detections(), list)
    assert isinstance(basic_result.has_nsfw(), bool)


def test_basic_tier_exposes_image_level_product_fields(basic_result):
    assert basic_result.is_nsfw in {True, False, None}
    assert basic_result.moderation.reason
    if basic_result.scene is not None:
        assert basic_result.scene.type is None or isinstance(basic_result.scene.type, str)
        assert basic_result.scene.intimacy is None or isinstance(basic_result.scene.intimacy, str)
    assert basic_result.caption is None or isinstance(basic_result.caption, str)
    if basic_result.nouns is not None:
        assert isinstance(basic_result.nouns.consensus, list)
        assert isinstance(basic_result.nouns.validated, list)
        assert isinstance(basic_result.nouns.regions, list)
    if basic_result.verbs is not None:
        assert isinstance(basic_result.verbs.consensus, list)


def test_basic_tier_exposes_services_namespace(basic_result):
    assert basic_result.services.nudenet is basic_result.nudenet
    assert "nudenet" in basic_result.services.names()


def test_all_submitted_services_have_results(basic_result):
    for service in basic_result.services_submitted:
        if service in basic_result.services_failed:
            continue
        assert getattr(basic_result, service) is not None, f"Missing result for service: {service}"


def test_analyze_services_match_tier_config(basic_result, basic_tiers):
    submitted = set(basic_result.services_submitted)
    tier_services = set(basic_tiers["basic"])
    assert {"colors", "content_analysis", "metadata", "nsfw2", "nudenet", "yolo_v8"}.issubset(submitted)
    assert submitted.issubset(tier_services)


def test_basic_submits_current_baseline_services(basic_result, basic_tiers):
    assert set(basic_result.services_submitted) == set(basic_tiers["basic"])
