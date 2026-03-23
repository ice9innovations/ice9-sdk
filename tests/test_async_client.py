import io
import pytest
import httpx

from ice9 import AsyncIce9
from ice9.exceptions import (
    AnalysisTimeoutError,
    AuthError,
    Ice9Error,
    ImageRejectedError,
    PartialResultError,
    RateLimitError,
)

from .conftest import ANALYZE_RESPONSE, SERVICES_RESPONSE, STATUS_COMPLETE, TIERS_RESPONSE

pytestmark = pytest.mark.asyncio

BASE = "https://api.ice9.ai"


# ---------------------------------------------------------------------------
# Helpers

def make_client(**kwargs):
    return AsyncIce9(api_key="ice9_test", **kwargs)


# ---------------------------------------------------------------------------
# Initialization

@pytest.mark.asyncio
async def test_init_requires_key(monkeypatch):
    monkeypatch.delenv("ICE9_API_KEY", raising=False)
    with pytest.raises(AuthError):
        AsyncIce9()


@pytest.mark.asyncio
async def test_init_accepts_env_var(monkeypatch):
    monkeypatch.setenv("ICE9_API_KEY", "ice9_from_env")
    client = AsyncIce9()
    assert client._api_key == "ice9_from_env"


@pytest.mark.asyncio
async def test_init_explicit_key_takes_precedence(monkeypatch):
    monkeypatch.setenv("ICE9_API_KEY", "ice9_from_env")
    client = AsyncIce9(api_key="ice9_explicit")
    assert client._api_key == "ice9_explicit"


@pytest.mark.asyncio
async def test_init_strips_trailing_slash_from_base_url():
    client = AsyncIce9(api_key="ice9_test", base_url="https://example.com/")
    assert client._base_url == "https://example.com"


# ---------------------------------------------------------------------------
# Context manager

async def test_context_manager_creates_client():
    async with make_client() as client:
        assert client._client is not None


async def test_context_manager_closes_client():
    client = make_client()
    async with client:
        pass
    assert client._client is None


async def test_aclose_resets_client_to_none():
    client = make_client()
    await client.__aenter__()
    await client.aclose()
    assert client._client is None


# ---------------------------------------------------------------------------
# tiers()

async def test_tiers_returns_dict(respx_mock):
    respx_mock.get(f"{BASE}/tiers").mock(return_value=httpx.Response(200, json=TIERS_RESPONSE))

    async with make_client() as client:
        result = await client.tiers()
        assert "free" in result
        assert "nudenet" in result["free"]


async def test_tiers_raises_on_server_error(respx_mock):
    respx_mock.get(f"{BASE}/tiers").mock(return_value=httpx.Response(500, json={"error": "down"}))

    async with make_client() as client:
        with pytest.raises(Ice9Error, match="500"):
            await client.tiers()


async def test_tiers_uses_detail_field_when_error_missing(respx_mock):
    respx_mock.get(f"{BASE}/tiers").mock(
        return_value=httpx.Response(400, json={"detail": "bad tier request"})
    )

    async with make_client() as client:
        with pytest.raises(Ice9Error, match="bad tier request"):
            await client.tiers()


# ---------------------------------------------------------------------------
# services()

async def test_services_returns_list(respx_mock):
    respx_mock.get(f"{BASE}/services").mock(return_value=httpx.Response(200, json=SERVICES_RESPONSE))

    async with make_client() as client:
        result = await client.services()
        assert isinstance(result, list)
        assert "colors" in result
        assert "nudenet" in result


async def test_services_raises_on_server_error(respx_mock):
    respx_mock.get(f"{BASE}/services").mock(return_value=httpx.Response(500, json={"error": "down"}))

    async with make_client() as client:
        with pytest.raises(Ice9Error, match="500"):
            await client.services()


# ---------------------------------------------------------------------------
# get_result()

async def test_get_result_returns_analysis_result(respx_mock):
    respx_mock.get(f"{BASE}/results/42").mock(return_value=httpx.Response(200, json=STATUS_COMPLETE))

    async with make_client() as client:
        result = await client.get_result(42)

    assert result.image_id == 42
    assert result.nudenet is not None
    assert result.colors is not None
    assert result.services_failed == {}


async def test_get_result_404_raises_ice9_error(respx_mock):
    respx_mock.get(f"{BASE}/results/999").mock(
        return_value=httpx.Response(404, json={"error": "Image not found"})
    )

    async with make_client() as client:
        with pytest.raises(Ice9Error, match="not found"):
            await client.get_result(999)


async def test_get_result_401_raises_auth_error(respx_mock):
    respx_mock.get(f"{BASE}/results/42").mock(
        return_value=httpx.Response(401, json={"error": "Authentication required"})
    )

    async with make_client() as client:
        with pytest.raises(AuthError):
            await client.get_result(42)


async def test_get_result_429_raises_rate_limit(respx_mock):
    respx_mock.get(f"{BASE}/results/42").mock(
        return_value=httpx.Response(
            429,
            json={"error": "rate limit exceeded"},
            headers={"Retry-After": "5"},
        )
    )

    async with make_client() as client:
        with pytest.raises(RateLimitError) as exc_info:
            await client.get_result(42)
    assert exc_info.value.retry_after == 5.0


async def test_get_result_500_raises_ice9_error(respx_mock):
    respx_mock.get(f"{BASE}/results/42").mock(
        return_value=httpx.Response(500, json={"error": "internal error"})
    )

    async with make_client() as client:
        with pytest.raises(Ice9Error):
            await client.get_result(42)


# ---------------------------------------------------------------------------
# analyze() — happy path

async def test_analyze_returns_analysis_result(respx_mock, png_file):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=STATUS_COMPLETE))

    async with make_client() as client:
        result = await client.analyze(png_file)

    assert result.image_id == 42
    assert result.nudenet is not None
    assert result.colors is not None
    assert result.services_failed == {}


async def test_analyze_accepts_path_string(respx_mock, png_file):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=STATUS_COMPLETE))

    async with make_client() as client:
        result = await client.analyze(str(png_file))

    assert result.image_id == 42


async def test_analyze_accepts_file_object(respx_mock, png_bytes_io):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=STATUS_COMPLETE))

    async with make_client() as client:
        result = await client.analyze(png_bytes_io)

    assert result.image_id == 42


async def test_analyze_accepts_url(respx_mock):
    from .conftest import MINIMAL_PNG

    # Mock the URL download
    respx_mock.get("https://example.com/photo.jpg").mock(
        return_value=httpx.Response(200, content=MINIMAL_PNG, headers={"Content-Type": "image/jpeg"})
    )
    # Mock the API submission
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=STATUS_COMPLETE))

    async with make_client() as client:
        result = await client.analyze("https://example.com/photo.jpg")

    assert result.image_id == 42


async def test_analyze_url_not_found(respx_mock):
    respx_mock.get("https://example.com/missing.jpg").mock(return_value=httpx.Response(404))

    async with make_client() as client:
        with pytest.raises(ImageRejectedError, match="not found at URL"):
            await client.analyze("https://example.com/missing.jpg")


async def test_analyze_url_not_an_image(respx_mock):
    respx_mock.get("https://example.com/file.txt").mock(
        return_value=httpx.Response(200, content=b"not an image", headers={"Content-Type": "text/plain"})
    )

    async with make_client() as client:
        with pytest.raises(ImageRejectedError, match="does not point to an image"):
            await client.analyze("https://example.com/file.txt")


async def test_analyze_polls_until_complete(respx_mock, png_file):
    """Verify the client polls multiple times before is_complete."""
    import copy
    in_progress = copy.deepcopy(STATUS_COMPLETE)
    in_progress["is_complete"] = False
    in_progress["services_pending"] = ["nudenet"]
    in_progress["progress"] = "4/5"

    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))

    # Mock two status responses: first in-progress, then complete
    status_route = respx_mock.get(f"{BASE}/status/42")
    status_route.side_effect = [
        httpx.Response(200, json=in_progress),
        httpx.Response(200, json=STATUS_COMPLETE),
    ]

    async with make_client() as client:
        client.POLL_INTERVAL = 0  # don't sleep in tests
        result = await client.analyze(png_file)

    assert result.image_id == 42


# ---------------------------------------------------------------------------
# analyze() — error paths on /analyze

async def test_analyze_401_raises_auth_error(respx_mock, png_file):
    respx_mock.post(f"{BASE}/analyze").mock(
        return_value=httpx.Response(401, json={"error": "Authentication required"})
    )

    async with make_client() as client:
        with pytest.raises(AuthError):
            await client.analyze(png_file)


async def test_analyze_400_raises_image_rejected(respx_mock, png_file):
    respx_mock.post(f"{BASE}/analyze").mock(
        return_value=httpx.Response(400, json={"error": "File must be an image"})
    )

    async with make_client() as client:
        with pytest.raises(ImageRejectedError, match="File must be an image"):
            await client.analyze(png_file)


async def test_analyze_429_raises_rate_limit(respx_mock, png_file):
    respx_mock.post(f"{BASE}/analyze").mock(
        return_value=httpx.Response(
            429,
            json={"error": "rate limit exceeded"},
            headers={"Retry-After": "5"},
        )
    )

    async with make_client() as client:
        with pytest.raises(RateLimitError) as exc_info:
            await client.analyze(png_file)
    assert exc_info.value.retry_after == 5.0


async def test_analyze_500_raises_ice9_error(respx_mock, png_file):
    respx_mock.post(f"{BASE}/analyze").mock(
        return_value=httpx.Response(500, json={"error": "internal error"})
    )

    async with make_client() as client:
        with pytest.raises(Ice9Error):
            await client.analyze(png_file)


# ---------------------------------------------------------------------------
# analyze() — error paths on /status

async def test_status_401_raises_auth_error(respx_mock, png_file):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(
        return_value=httpx.Response(401, json={"error": "Authentication required"})
    )

    async with make_client() as client:
        with pytest.raises(AuthError):
            await client.analyze(png_file)


async def test_status_404_raises_ice9_error(respx_mock, png_file):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(
        return_value=httpx.Response(404, json={"error": "Image not found"})
    )

    async with make_client() as client:
        with pytest.raises(Ice9Error, match="not found"):
            await client.analyze(png_file)


async def test_status_429_backs_off_and_retries(respx_mock, png_file):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))

    status_route = respx_mock.get(f"{BASE}/status/42")
    status_route.side_effect = [
        httpx.Response(429, json={"error": "rate limit"}, headers={"Retry-After": "0"}),
        httpx.Response(200, json=STATUS_COMPLETE),
    ]

    async with make_client() as client:
        client.POLL_INTERVAL = 0
        result = await client.analyze(png_file)

    assert result.image_id == 42


# ---------------------------------------------------------------------------
# analyze() — timeout

async def test_analyze_timeout_raises(respx_mock, png_file):
    import copy
    in_progress = copy.deepcopy(STATUS_COMPLETE)
    in_progress["is_complete"] = False

    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    # Always return in-progress
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=in_progress))

    async with make_client() as client:
        client.POLL_INTERVAL = 0
        with pytest.raises(AnalysisTimeoutError):
            await client.analyze(png_file, timeout=0.001)


# ---------------------------------------------------------------------------
# analyze() — partial failure

async def test_partial_failure_raises_partial_result_error(respx_mock, png_file):
    import copy
    partial_status = copy.deepcopy(STATUS_COMPLETE)
    partial_status["services_failed"] = {"nudenet": "worker crashed"}
    partial_status["service_results"].pop("nudenet")

    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=partial_status))

    with pytest.warns(UserWarning, match="failed services: \\['nudenet'\\]"):
        async with make_client() as client:
            with pytest.raises(PartialResultError) as exc_info:
                await client.analyze(png_file)

    # The partial result is still accessible on the exception
    assert exc_info.value.result.image_id == 42
    assert exc_info.value.result.nudenet is None
    assert exc_info.value.result.colors is not None


async def test_raise_on_partial_false_returns_result_instead_of_raising(respx_mock, png_file):
    import copy
    partial_status = copy.deepcopy(STATUS_COMPLETE)
    partial_status["services_failed"] = {"nudenet": "worker crashed"}
    partial_status["service_results"].pop("nudenet")

    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=partial_status))

    with pytest.warns(UserWarning, match="failed services: \\['nudenet'\\]"):
        async with make_client() as client:
            # Should not raise — just return the result with services_failed populated
            result = await client.analyze(png_file, raise_on_partial=False)

    assert result.image_id == 42
    assert result.services_failed == {"nudenet": "worker crashed"}
    assert result.nudenet is None
    assert result.colors is not None


async def test_raise_on_partial_false_logs_warning(respx_mock, png_file, caplog):
    import copy
    import logging
    partial_status = copy.deepcopy(STATUS_COMPLETE)
    partial_status["services_failed"] = {"yolo": "timeout"}
    partial_status["service_results"].pop("yolo", None)

    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=partial_status))

    with pytest.warns(UserWarning, match="failed services: \\['yolo'\\]"):
        with caplog.at_level(logging.WARNING, logger="ice9"):
            async with make_client() as client:
                result = await client.analyze(png_file, raise_on_partial=False)

    assert "failed services" in caplog.text.lower()
    assert "yolo" in caplog.text


# ---------------------------------------------------------------------------
# analyze(stream=True)
# Note: Full streaming tests are complex with httpx mocking.
# These tests verify the basic structure. Integration tests cover the full flow.

async def test_stream_returns_async_generator(respx_mock, png_file):
    """Verify that stream=True returns an async generator."""
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))

    # Mock SSE stream
    import json as _json
    sse_body = (
        b"event: service_complete\n"
        b"data: " + _json.dumps({"service": "nudenet", "result": {"detections": []}}).encode() + b"\n\n"
        b"event: complete\n"
        b"data: " + _json.dumps({**STATUS_COMPLETE, "is_complete": True}).encode() + b"\n\n"
    )

    respx_mock.get(f"{BASE}/stream/42").mock(
        return_value=httpx.Response(200, content=sse_body, headers={"Content-Type": "text/event-stream"})
    )

    async with make_client() as client:
        generator = await client.analyze(png_file, stream=True)
        results = []
        async for result in generator:
            results.append(result)

        # Should yield at least the final result
        assert len(results) >= 1
        assert results[-1].is_complete is True
