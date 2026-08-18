"""
Integration tests — async client parity.

Verifies that AsyncIce9 can exercise the same public API surface against the
real API for at least one tier.

Run with:
    ICE9_API_KEY=ice9_... pytest tests/integration/test_async_client.py -v
"""
import pytest

from ice9 import AnalysisResult, AsyncIce9


pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
async def async_client(api_key, base_url):
    async with AsyncIce9(api_key=api_key, base_url=base_url) as client:
        yield client


@pytest.fixture
async def async_free_result(async_client, test_image):
    return await async_client.analyze(test_image, tier="basic")


@pytest.fixture
async def async_free_status(async_client, async_free_result):
    return await async_client.get_status(async_free_result.image_id)


@pytest.fixture
async def async_retrieved_free_result(async_client, async_free_result):
    return await async_client.get_result(async_free_result.image_id)


@pytest.fixture
async def async_stream_results(async_client, test_image):
    stream = await async_client.analyze(test_image, tier="basic", stream=True)
    results = []
    async for result in stream:
        results.append(result)
    return results


async def test_async_services_returns_catalog(async_client):
    services = await async_client.services()
    assert isinstance(services, list)
    assert len(services) > 0


async def test_async_analyze_returns_result(async_free_result):
    assert isinstance(async_free_result, AnalysisResult)
    assert async_free_result.image_id > 0
    assert async_free_result.services_failed == {}


async def test_async_get_status_returns_completed_payload(async_free_status, async_free_result):
    assert async_free_status["image_id"] == async_free_result.image_id
    assert async_free_status["is_complete"] is True


async def test_async_get_result_round_trips_analysis_result(async_retrieved_free_result, async_free_result):
    assert isinstance(async_retrieved_free_result, AnalysisResult)
    assert async_retrieved_free_result.image_id == async_free_result.image_id
    assert set(async_retrieved_free_result.services_submitted) == set(async_free_result.services_submitted)


async def test_async_streaming_returns_complete_final_result(async_stream_results):
    assert len(async_stream_results) >= 1
    assert async_stream_results[-1].is_complete is True


async def test_async_streaming_yields_partial_before_complete(async_stream_results):
    assert any(result.is_complete is False for result in async_stream_results[:-1])
