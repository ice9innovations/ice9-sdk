import io
import pytest
import httpx
import respx

from ice9 import Ice9
from ice9.exceptions import (
    AnalysisTimeoutError,
    AuthError,
    Ice9Error,
    ImageRejectedError,
    PartialResultError,
    RateLimitError,
)

from .conftest import ANALYZE_RESPONSE, SERVICES_RESPONSE, STATUS_COMPLETE, TIERS_RESPONSE

BASE = "https://api.ice9.ai"


# ---------------------------------------------------------------------------
# Helpers

def make_client(**kwargs):
    return Ice9(api_key="ice9_test", **kwargs)


def mock_final_result(respx_mock, payload=STATUS_COMPLETE, image_id=42):
    respx_mock.get(f"{BASE}/results/{image_id}").mock(
        return_value=httpx.Response(200, json=payload)
    )


# ---------------------------------------------------------------------------
# Initialization

def test_init_requires_key(monkeypatch):
    monkeypatch.delenv("ICE9_API_KEY", raising=False)
    with pytest.raises(AuthError):
        Ice9()


def test_init_accepts_env_var(monkeypatch):
    monkeypatch.setenv("ICE9_API_KEY", "ice9_from_env")
    client = Ice9()
    assert client._api_key == "ice9_from_env"


def test_init_explicit_key_takes_precedence(monkeypatch):
    monkeypatch.setenv("ICE9_API_KEY", "ice9_from_env")
    client = Ice9(api_key="ice9_explicit")
    assert client._api_key == "ice9_explicit"


def test_init_strips_trailing_slash_from_base_url():
    client = Ice9(api_key="ice9_test", base_url="https://example.com/")
    assert client._base_url == "https://example.com"


# ---------------------------------------------------------------------------
# Context manager / close

def test_context_manager_returns_client():
    with make_client() as client:
        assert isinstance(client, Ice9)


def test_close_closes_underlying_client():
    client = make_client()
    client.close()
    assert client._client.is_closed


# ---------------------------------------------------------------------------
# tiers()

def test_tiers_returns_dict(respx_mock):
    respx_mock.get(f"{BASE}/tiers").mock(return_value=httpx.Response(200, json=TIERS_RESPONSE))
    client = make_client()
    result = client.tiers()
    assert "free" in result
    assert "nudenet" in result["free"]


def test_tiers_raises_on_server_error(respx_mock):
    respx_mock.get(f"{BASE}/tiers").mock(return_value=httpx.Response(500, json={"error": "down"}))
    with pytest.raises(Ice9Error, match="500"):
        make_client().tiers()


def test_tiers_uses_detail_field_when_error_missing(respx_mock):
    respx_mock.get(f"{BASE}/tiers").mock(
        return_value=httpx.Response(400, json={"detail": "bad tier request"})
    )
    with pytest.raises(Ice9Error, match="bad tier request"):
        make_client().tiers()


# ---------------------------------------------------------------------------
# services()

def test_services_returns_list(respx_mock):
    respx_mock.get(f"{BASE}/services").mock(return_value=httpx.Response(200, json=SERVICES_RESPONSE))
    client = make_client()
    result = client.services()
    assert isinstance(result, list)
    assert "colors" in result
    assert "nudenet" in result


def test_services_raises_on_server_error(respx_mock):
    respx_mock.get(f"{BASE}/services").mock(return_value=httpx.Response(500, json={"error": "down"}))
    with pytest.raises(Ice9Error, match="500"):
        make_client().services()


# ---------------------------------------------------------------------------
# get_result()

def test_get_result_returns_analysis_result(respx_mock):
    respx_mock.get(f"{BASE}/results/42").mock(return_value=httpx.Response(200, json=STATUS_COMPLETE))

    result = make_client().get_result(42)

    assert result.image_id == 42
    assert result.nudenet is not None
    assert result.colors is not None
    assert result.services_failed == {}


def test_get_result_404_raises_ice9_error(respx_mock):
    respx_mock.get(f"{BASE}/results/999").mock(return_value=httpx.Response(404, json={"error": "Image not found"}))
    with pytest.raises(Ice9Error, match="not found"):
        make_client().get_result(999)


def test_get_result_401_raises_auth_error(respx_mock):
    respx_mock.get(f"{BASE}/results/42").mock(return_value=httpx.Response(401, json={"error": "Authentication required"}))
    with pytest.raises(AuthError):
        make_client().get_result(42)


def test_get_result_429_raises_rate_limit(respx_mock):
    respx_mock.get(f"{BASE}/results/42").mock(
        return_value=httpx.Response(
            429,
            json={"error": "rate limit exceeded"},
            headers={"Retry-After": "5"},
        )
    )
    with pytest.raises(RateLimitError) as exc_info:
        make_client().get_result(42)
    assert exc_info.value.retry_after == 5.0


def test_get_result_500_raises_ice9_error(respx_mock):
    respx_mock.get(f"{BASE}/results/42").mock(return_value=httpx.Response(500, json={"error": "internal error"}))
    with pytest.raises(Ice9Error):
        make_client().get_result(42)


# ---------------------------------------------------------------------------
# analyze() — happy path

def test_analyze_returns_analysis_result(png_file, respx_mock):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=STATUS_COMPLETE))
    mock_final_result(respx_mock)

    result = make_client().analyze(png_file)

    assert result.image_id == 42
    assert result.nudenet is not None
    assert result.colors is not None
    assert result.services_failed == {}


def test_analyze_accepts_path_string(png_file, respx_mock):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=STATUS_COMPLETE))
    mock_final_result(respx_mock)

    result = make_client().analyze(str(png_file))
    assert result.image_id == 42


def test_analyze_accepts_file_object(png_bytes_io, respx_mock):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=STATUS_COMPLETE))
    mock_final_result(respx_mock)

    result = make_client().analyze(png_bytes_io)
    assert result.image_id == 42


def test_analyze_accepts_url(respx_mock):
    import base64
    from .conftest import MINIMAL_PNG

    # Mock the URL download
    respx_mock.get("https://example.com/photo.jpg").mock(
        return_value=httpx.Response(
            200,
            content=MINIMAL_PNG,
            headers={"Content-Type": "image/jpeg"},
        )
    )
    # Mock the API submission
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=STATUS_COMPLETE))
    mock_final_result(respx_mock)

    result = make_client().analyze("https://example.com/photo.jpg")
    assert result.image_id == 42


def test_analyze_url_not_found(respx_mock):
    respx_mock.get("https://example.com/missing.jpg").mock(return_value=httpx.Response(404))

    with pytest.raises(ImageRejectedError, match="not found at URL"):
        make_client().analyze("https://example.com/missing.jpg")


def test_analyze_url_not_an_image(respx_mock):
    respx_mock.get("https://example.com/file.txt").mock(
        return_value=httpx.Response(
            200,
            content=b"not an image",
            headers={"Content-Type": "text/plain"},
        )
    )

    with pytest.raises(ImageRejectedError, match="does not point to an image"):
        make_client().analyze("https://example.com/file.txt")


def test_analyze_passes_tier(png_file, respx_mock):
    post_route = respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=STATUS_COMPLETE))
    mock_final_result(respx_mock)

    make_client().analyze(png_file, tier="free")

    # Verify tier was sent in the request body
    assert post_route.called
    request = post_route.calls[0].request
    assert b"free" in request.content


def test_analyze_omits_tier_when_not_specified(png_file, respx_mock):
    post_route = respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=STATUS_COMPLETE))
    mock_final_result(respx_mock)

    make_client().analyze(png_file)

    # Verify tier was NOT sent in the request body
    assert post_route.called
    request = post_route.calls[0].request
    assert b"tier" not in request.content


def test_analyze_polls_until_complete(png_file, respx_mock):
    """Verify the client polls multiple times before is_complete."""
    import copy
    in_progress = copy.deepcopy(STATUS_COMPLETE)
    in_progress["is_complete"] = False
    in_progress["services_pending"] = ["nudenet"]
    in_progress["progress"] = "4/5"

    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(side_effect=[
        httpx.Response(200, json=in_progress),
        httpx.Response(200, json=STATUS_COMPLETE),
    ])
    mock_final_result(respx_mock)

    client = make_client()
    client.POLL_INTERVAL = 0  # don't sleep in tests
    result = client.analyze(png_file)

    assert result.image_id == 42


# ---------------------------------------------------------------------------
# analyze() — error paths on /analyze

def test_analyze_401_raises_auth_error(png_file, respx_mock):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(401, json={"error": "Authentication required"}))
    with pytest.raises(AuthError):
        make_client().analyze(png_file)


def test_analyze_400_raises_image_rejected(png_file, respx_mock):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(400, json={"error": "File must be an image"}))
    with pytest.raises(ImageRejectedError, match="File must be an image"):
        make_client().analyze(png_file)


def test_analyze_429_raises_rate_limit(png_file, respx_mock):
    respx_mock.post(f"{BASE}/analyze").mock(
        return_value=httpx.Response(
            429,
            json={"error": "rate limit exceeded"},
            headers={"Retry-After": "5"},
        )
    )
    with pytest.raises(RateLimitError) as exc_info:
        make_client().analyze(png_file)
    assert exc_info.value.retry_after == 5.0


def test_analyze_429_without_retry_after_header(png_file, respx_mock):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(429, json={"error": "rate limit"}))
    with pytest.raises(RateLimitError) as exc_info:
        make_client().analyze(png_file)
    assert exc_info.value.retry_after is None


def test_analyze_500_raises_ice9_error(png_file, respx_mock):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(500, json={"error": "internal error"}))
    with pytest.raises(Ice9Error):
        make_client().analyze(png_file)


def test_analyze_connection_error_raises_ice9_error(png_file):
    client = make_client(base_url="http://localhost:1")  # nothing listening here
    with pytest.raises(Ice9Error, match="connect"):
        client.analyze(png_file)


# ---------------------------------------------------------------------------
# analyze() — error paths on /status

def test_status_401_raises_auth_error(png_file, respx_mock):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(401, json={"error": "Authentication required"}))
    with pytest.raises(AuthError):
        make_client().analyze(png_file)


def test_status_404_raises_ice9_error(png_file, respx_mock):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(404, json={"error": "Image not found"}))
    with pytest.raises(Ice9Error, match="not found"):
        make_client().analyze(png_file)


def test_status_429_backs_off_and_retries(png_file, respx_mock):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(side_effect=[
        httpx.Response(429, json={"error": "rate limit"}, headers={"Retry-After": "0"}),
        httpx.Response(200, json=STATUS_COMPLETE),
    ])
    mock_final_result(respx_mock)

    client = make_client()
    client.POLL_INTERVAL = 0
    result = client.analyze(png_file)
    assert result.image_id == 42


# ---------------------------------------------------------------------------
# analyze() — timeout

def test_analyze_timeout_raises(png_file, respx_mock):
    import copy
    in_progress = copy.deepcopy(STATUS_COMPLETE)
    in_progress["is_complete"] = False

    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    # Return incomplete responses indefinitely
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=in_progress))

    client = make_client()
    client.POLL_INTERVAL = 0
    with pytest.raises(AnalysisTimeoutError):
        client.analyze(png_file, timeout=0.001)


# ---------------------------------------------------------------------------
# analyze() — partial failure

def test_partial_failure_raises_partial_result_error(png_file, respx_mock):
    import copy
    partial_status = copy.deepcopy(STATUS_COMPLETE)
    partial_status["services_failed"] = {"nudenet": "worker crashed"}
    partial_status["service_results"].pop("nudenet")

    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=partial_status))
    mock_final_result(respx_mock, partial_status)

    with pytest.warns(UserWarning, match="failed services: \\['nudenet'\\]"):
        with pytest.raises(PartialResultError) as exc_info:
            make_client().analyze(png_file)

    # The partial result is still accessible on the exception
    assert exc_info.value.result.image_id == 42
    assert exc_info.value.result.nudenet is None
    assert exc_info.value.result.colors is not None


def test_partial_result_contains_succeeded_services(png_file, respx_mock):
    import copy
    partial_status = copy.deepcopy(STATUS_COMPLETE)
    partial_status["services_failed"] = {"ocr": "timeout"}
    partial_status["service_results"].pop("ocr")

    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=partial_status))
    mock_final_result(respx_mock, partial_status)

    with pytest.warns(UserWarning, match="failed services: \\['ocr'\\]"):
        try:
            make_client().analyze(png_file)
        except PartialResultError as exc:
            result = exc.result
            assert result.nudenet is not None
            assert result.ocr is None


def test_raise_on_partial_false_returns_result_instead_of_raising(png_file, respx_mock):
    import copy
    partial_status = copy.deepcopy(STATUS_COMPLETE)
    partial_status["services_failed"] = {"nudenet": "worker crashed"}
    partial_status["service_results"].pop("nudenet")

    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=partial_status))
    mock_final_result(respx_mock, partial_status)

    # Should not raise — just return the result with services_failed populated
    with pytest.warns(UserWarning, match="failed services: \\['nudenet'\\]"):
        result = make_client().analyze(png_file, raise_on_partial=False)

    assert result.image_id == 42
    assert result.services_failed == {"nudenet": "worker crashed"}
    assert result.nudenet is None
    assert result.colors is not None


def test_raise_on_partial_false_logs_warning(png_file, respx_mock, caplog):
    import copy
    import logging
    partial_status = copy.deepcopy(STATUS_COMPLETE)
    partial_status["services_failed"] = {"yolo": "timeout"}
    partial_status["service_results"].pop("yolo", None)

    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=partial_status))
    mock_final_result(respx_mock, partial_status)

    with pytest.warns(UserWarning, match="failed services: \\['yolo'\\]"):
        with caplog.at_level(logging.WARNING, logger="ice9"):
            result = make_client().analyze(png_file, raise_on_partial=False)

    assert "failed services" in caplog.text.lower()
    assert "yolo" in caplog.text


# ---------------------------------------------------------------------------
# analyze(stream=True)

import json as _json


def _make_sse_body(*events):
    """Build SSE response bytes from (event_type, data_dict) pairs.

    Each event is terminated by a blank line (\\n\\n) so that splitlines()
    inside requests' iter_lines() produces the empty-string separator needed
    to dispatch the event.
    """
    parts = []
    for event_type, data in events:
        parts.append(f"event: {event_type}\ndata: {_json.dumps(data)}\n\n")
    return "".join(parts).encode()


_STREAM_COMPLETE_PAYLOAD = {
    **STATUS_COMPLETE,
    "is_complete": True,
}

_SSE_HAPPY_PATH = _make_sse_body(
    ("service_complete", {"service": "nudenet", "result": {"detections": []}}),
    ("service_complete", {"service": "colors",  "result": {"dominant": ["#ffffff"]}}),
    ("complete", _STREAM_COMPLETE_PAYLOAD),
)


def test_stream_yields_partial_results(png_file, respx_mock):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/stream/42").mock(
        return_value=httpx.Response(
            200,
            content=_SSE_HAPPY_PATH,
            headers={"Content-Type": "text/event-stream"},
        )
    )
    mock_final_result(respx_mock)

    partials = list(make_client().analyze(png_file, stream=True))

    # Two service_complete events + one complete event = 3 yields
    assert len(partials) == 3


def test_stream_partial_yields_have_is_complete_false(png_file, respx_mock):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/stream/42").mock(
        return_value=httpx.Response(
            200,
            content=_SSE_HAPPY_PATH,
            headers={"Content-Type": "text/event-stream"},
        )
    )
    mock_final_result(respx_mock)

    partials = list(make_client().analyze(png_file, stream=True))

    assert partials[0].is_complete is False
    assert partials[1].is_complete is False
    assert partials[2].is_complete is True


def test_stream_partial_results_accumulate(png_file, respx_mock):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/stream/42").mock(
        return_value=httpx.Response(
            200,
            content=_SSE_HAPPY_PATH,
            headers={"Content-Type": "text/event-stream"},
        )
    )
    mock_final_result(respx_mock)

    partials = list(make_client().analyze(png_file, stream=True))

    # First partial: only nudenet
    assert partials[0].nudenet is not None
    assert partials[0].colors is None

    # Second partial: nudenet + colors
    assert partials[1].nudenet is not None
    assert partials[1].colors is not None


def test_stream_final_result_from_complete_event(png_file, respx_mock):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/stream/42").mock(
        return_value=httpx.Response(
            200,
            content=_SSE_HAPPY_PATH,
            headers={"Content-Type": "text/event-stream"},
        )
    )
    mock_final_result(respx_mock)

    partials = list(make_client().analyze(png_file, stream=True))
    final = partials[-1]

    assert final.image_id == 42
    assert final.is_complete is True
    assert final.services_failed == {}


def test_stream_final_result_fills_missing_services_submitted_from_accumulated_events(png_file, respx_mock):
    import copy

    final_payload = copy.deepcopy(_STREAM_COMPLETE_PAYLOAD)
    final_payload["services_submitted"] = []

    sse_body = _make_sse_body(
        ("service_complete", {"service": "nudenet", "result": {"detections": []}}),
        ("service_complete", {"service": "colors", "result": {"dominant": ["#ffffff"]}}),
        ("complete", final_payload),
    )

    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/stream/42").mock(
        return_value=httpx.Response(
            200,
            content=sse_body,
            headers={"Content-Type": "text/event-stream"},
        )
    )
    mock_final_result(respx_mock)

    final = list(make_client().analyze(png_file, stream=True))[-1]

    assert final.is_complete is True
    assert set(final.services_submitted) >= {"nudenet", "colors"}


def test_stream_timeout_event_raises(png_file, respx_mock):
    body = _make_sse_body(("timeout", {"reason": "processing timed out"}))
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/stream/42").mock(
        return_value=httpx.Response(
            200,
            content=body,
            headers={"Content-Type": "text/event-stream"},
        )
    )

    with pytest.raises(AnalysisTimeoutError):
        list(make_client().analyze(png_file, stream=True))


def test_stream_keepalive_comments_ignored(png_file, respx_mock):
    # Keepalive comment between events should not break parsing
    body = (
        b": keepalive\n\n"
        + _make_sse_body(
            ("service_complete", {"service": "nudenet", "result": {"detections": []}}),
            ("complete", _STREAM_COMPLETE_PAYLOAD),
        )
    )
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/stream/42").mock(
        return_value=httpx.Response(
            200,
            content=body,
            headers={"Content-Type": "text/event-stream"},
        )
    )
    mock_final_result(respx_mock)

    partials = list(make_client().analyze(png_file, stream=True))
    assert len(partials) == 2
    assert partials[-1].is_complete is True


def test_stream_401_raises_auth_error(png_file, respx_mock):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/stream/42").mock(
        return_value=httpx.Response(401, json={"error": "Authentication required"})
    )

    with pytest.raises(AuthError):
        list(make_client().analyze(png_file, stream=True))


def test_stream_404_raises_ice9_error(png_file, respx_mock):
    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/stream/42").mock(
        return_value=httpx.Response(404, json={"error": "Image not found"})
    )

    with pytest.raises(Ice9Error, match="not found"):
        list(make_client().analyze(png_file, stream=True))


def test_stream_with_failed_services_raises_partial_result_error(png_file, respx_mock):
    import copy
    partial_complete = copy.deepcopy(_STREAM_COMPLETE_PAYLOAD)
    partial_complete["services_failed"] = {"yolo": "worker crashed"}
    partial_complete["service_results"].pop("yolo", None)

    sse_body = _make_sse_body(
        ("service_complete", {"service": "nudenet", "result": {"detections": []}}),
        ("complete", partial_complete),
    )

    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/stream/42").mock(
        return_value=httpx.Response(
            200,
            content=sse_body,
            headers={"Content-Type": "text/event-stream"},
        )
    )
    mock_final_result(respx_mock, partial_complete)

    with pytest.warns(UserWarning, match="failed services: \\['yolo'\\]"):
        with pytest.raises(PartialResultError) as exc_info:
            list(make_client().analyze(png_file, stream=True))

    assert exc_info.value.result.services_failed == {"yolo": "worker crashed"}


def test_stream_raise_on_partial_false_returns_result(png_file, respx_mock):
    import copy
    partial_complete = copy.deepcopy(_STREAM_COMPLETE_PAYLOAD)
    partial_complete["services_failed"] = {"ocr": "timeout"}
    partial_complete["service_results"].pop("ocr", None)

    sse_body = _make_sse_body(
        ("service_complete", {"service": "nudenet", "result": {"detections": []}}),
        ("complete", partial_complete),
    )

    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/stream/42").mock(
        return_value=httpx.Response(
            200,
            content=sse_body,
            headers={"Content-Type": "text/event-stream"},
        )
    )
    mock_final_result(respx_mock, partial_complete)

    # Should not raise — just yield the result with services_failed populated
    with pytest.warns(UserWarning, match="failed services: \\['ocr'\\]"):
        results = list(make_client().analyze(png_file, stream=True, raise_on_partial=False))
    final = results[-1]

    assert final.is_complete is True
    assert final.services_failed == {"ocr": "timeout"}
    assert final.nudenet is not None


def test_analyze_fetches_results_after_status_complete(png_file, respx_mock):
    import copy

    status_complete = copy.deepcopy(STATUS_COMPLETE)
    status_complete["service_results"].pop("content_analysis", None)

    results_complete = copy.deepcopy(STATUS_COMPLETE)

    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/status/42").mock(return_value=httpx.Response(200, json=status_complete))
    mock_final_result(respx_mock, results_complete)

    result = make_client().analyze(png_file)

    assert result.content_analysis is not None


def test_stream_fetches_results_after_complete_event(png_file, respx_mock):
    import copy

    final_payload = copy.deepcopy(_STREAM_COMPLETE_PAYLOAD)
    final_payload["service_results"].pop("content_analysis", None)

    sse_body = _make_sse_body(
        ("service_complete", {"service": "nudenet", "result": {"detections": []}}),
        ("complete", final_payload),
    )

    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/stream/42").mock(
        return_value=httpx.Response(
            200,
            content=sse_body,
            headers={"Content-Type": "text/event-stream"},
        )
    )
    mock_final_result(respx_mock, STATUS_COMPLETE)

    final = list(make_client().analyze(png_file, stream=True))[-1]

    assert final.content_analysis is not None


def test_stream_preserves_already_observed_services_if_results_lags(png_file, respx_mock):
    import copy

    sse_body = _make_sse_body(
        ("service_complete", {"service": "nudenet", "result": {"detections": []}}),
        ("service_complete", {"service": "colors", "result": {"dominant": ["#ffffff"]}}),
        ("complete", _STREAM_COMPLETE_PAYLOAD),
    )

    lagging_results = copy.deepcopy(STATUS_COMPLETE)
    lagging_results["service_results"].pop("colors", None)
    lagging_results["services_submitted"] = [s for s in lagging_results["services_submitted"] if s != "colors"]

    respx_mock.post(f"{BASE}/analyze").mock(return_value=httpx.Response(202, json=ANALYZE_RESPONSE))
    respx_mock.get(f"{BASE}/stream/42").mock(
        return_value=httpx.Response(
            200,
            content=sse_body,
            headers={"Content-Type": "text/event-stream"},
        )
    )
    mock_final_result(respx_mock, lagging_results)

    final = list(make_client().analyze(png_file, stream=True))[-1]

    assert final.colors is not None
    assert "colors" in final.services_submitted
