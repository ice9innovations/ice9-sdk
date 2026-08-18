"""
Integration tests — baseline tier.

Verifies that the SDK works end-to-end against the real API using the current
baseline tier. The basic tier is the moderation baseline, so nudenet and
content_analysis must be present.

Run with:
    ICE9_API_KEY=ice9_... pytest tests/integration/test_free_tier.py -v
"""
import pytest

from ice9 import Ice9, AnalysisResult


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def free_result(client, test_image):
    """One completed baseline analysis, shared across all tests in this module."""
    return client.analyze(test_image, tier="basic")


@pytest.fixture(scope="module")
def free_tiers(client):
    """Tier config, fetched once for the module."""
    return client.tiers()


@pytest.fixture(scope="module")
def free_services(client):
    """Service catalog, fetched once for the module."""
    return client.services()


@pytest.fixture(scope="module")
def free_status(client, free_result):
    """Raw /status payload for the completed baseline analysis."""
    return client.get_status(free_result.image_id)


@pytest.fixture(scope="module")
def retrieved_free_result(client, free_result):
    """Completed result fetched back from /results."""
    return client.get_result(free_result.image_id)


@pytest.fixture(scope="module")
def free_stream_results(client, test_image):
    """Streaming baseline submission, consumed once and shared across tests."""
    return list(client.analyze(test_image, tier="basic", stream=True))


# ---------------------------------------------------------------------------
# Tiers endpoint

def test_tiers_endpoint_includes_basic(free_tiers):
    assert "basic" in free_tiers
    assert isinstance(free_tiers["basic"], list)
    assert len(free_tiers["basic"]) > 0


def test_services_endpoint_returns_catalog(free_services, free_tiers):
    assert isinstance(free_services, list)
    assert len(free_services) > 0
    expected = {"colors", "content_analysis", "metadata", "nsfw2", "nudenet", "yolo_v8"}
    assert expected.issubset(set(free_services))
    assert "basic" in free_tiers
    assert len(set(free_tiers["basic"]) & set(free_services)) >= len(expected)


# ---------------------------------------------------------------------------
# Analysis result

def test_analyze_returns_result(free_result):
    assert isinstance(free_result, AnalysisResult)
    assert free_result.image_id > 0


def test_analyze_baseline_tier_is_complete(free_result):
    assert free_result.services_failed == {}


def test_analyze_nudenet_is_present(free_result):
    assert free_result.nudenet is not None


def test_baseline_tier_exposes_nsfw_helpers(free_result):
    assert isinstance(free_result.nsfw_detections(), list)
    assert isinstance(free_result.has_nsfw(), bool)


def test_baseline_tier_exposes_image_level_moderation_surface(free_result):
    assert free_result.is_nsfw in {True, False, None}
    assert free_result.moderation.reason
    if free_result.scene is not None:
        assert free_result.scene.type is None or isinstance(free_result.scene.type, str)
        assert free_result.scene.intimacy is None or isinstance(free_result.scene.intimacy, str)


def test_baseline_tier_exposes_services_namespace(free_result):
    assert free_result.services.nudenet is free_result.nudenet
    assert "nudenet" in free_result.services.names()


def test_all_submitted_services_have_results(free_result):
    for service in free_result.services_submitted:
        assert getattr(free_result, service) is not None, f"Missing result for service: {service}"


def test_analyze_services_match_tier_config(free_result, free_tiers):
    submitted = set(free_result.services_submitted)
    tier_services = set(free_tiers["basic"])
    assert {"colors", "content_analysis", "metadata", "nsfw2", "nudenet", "yolo_v8"}.issubset(submitted)
    assert submitted.issubset(tier_services)


def test_get_status_returns_completed_payload(free_status, free_result):
    assert free_status["image_id"] == free_result.image_id
    assert free_status["is_complete"] is True
    assert set(free_status["services_submitted"]) == set(free_result.services_submitted)


def test_get_result_round_trips_analysis_result(retrieved_free_result, free_result):
    assert isinstance(retrieved_free_result, AnalysisResult)
    assert retrieved_free_result.image_id == free_result.image_id
    assert set(retrieved_free_result.services_submitted) == set(free_result.services_submitted)


def test_streaming_returns_complete_final_result(free_stream_results, free_tiers):
    assert len(free_stream_results) >= 1
    assert free_stream_results[-1].is_complete is True
    submitted = set(free_stream_results[-1].services_submitted)
    tier_services = set(free_tiers["basic"])
    assert {"colors", "content_analysis", "metadata", "nsfw2", "nudenet", "yolo_v8"}.issubset(submitted)
    assert submitted.issubset(tier_services)


def test_streaming_yields_partial_before_complete(free_stream_results):
    assert any(result.is_complete is False for result in free_stream_results[:-1])


# ---------------------------------------------------------------------------
# image_group — needs its own submission since it uses a different group tag

def test_analyze_image_group_is_set(client, test_image):
    result = client.analyze(test_image, tier="basic", image_group="sdk-integration-test")
    assert result._raw.get("image_group") == "sdk-integration-test"
