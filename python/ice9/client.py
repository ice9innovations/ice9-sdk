from __future__ import annotations

import io
import json
import logging
import os
import time
from pathlib import Path
from typing import BinaryIO

import httpx

from .exceptions import (
    AuthError,
    AnalysisTimeoutError,
    Ice9Error,
    ImageRejectedError,
    PartialResultError,
    RateLimitError,
)
from .models import AnalysisResult

logger = logging.getLogger("ice9")
BASELINE_TIER = "basic"


class Ice9:
    """Client for the ice9 image analysis API.

    Usage::

        from ice9 import Ice9

        client = Ice9(api_key="ice9_...")
        result = client.analyze("photo.jpg")
        print(result.nudenet)

    The API key can also be set via the ICE9_API_KEY environment variable,
    in which case the ``api_key`` argument may be omitted.
    """

    DEFAULT_BASE_URL = "https://api.ice9.ai"
    DEFAULT_TIMEOUT = 30.0
    POLL_INTERVAL = 0.25
    DEFAULT_MAX_RETRIES = 3

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        resolved_key = api_key or os.environ.get("ICE9_API_KEY")
        if not resolved_key:
            raise AuthError(
                "No API key provided. Pass api_key= or set the ICE9_API_KEY "
                "environment variable."
            )

        self._api_key = resolved_key
        self._base_url = base_url.rstrip("/")
        self._default_timeout = timeout
        self._max_retries = max_retries
        self._client = httpx.Client(
            headers={"X-API-Key": self._api_key},
            timeout=httpx.Timeout(
                connect=10.0,   # fail fast if API is unreachable
                read=timeout,   # respect user timeout for response reading
                write=timeout,  # respect user timeout for large uploads
                pool=5.0,
            ),
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close the underlying HTTP client."""
        self._client.close()

    def _should_retry(self, exc: Exception, resp: httpx.Response | None = None) -> bool:
        """Determine if a request should be retried based on the error."""
        # Connection errors - transient network issues
        if isinstance(exc, httpx.ConnectError):
            return True
        # Timeout errors - might be transient
        if isinstance(exc, httpx.TimeoutException):
            return True
        # 5xx server errors - API might be temporarily down
        if resp and 500 <= resp.status_code < 600:
            return True
        # 429 rate limit - will retry with backoff
        if resp and resp.status_code == 429:
            return True
        return False

    def _retry_delay(self, attempt: int, resp: httpx.Response | None = None) -> float:
        """Calculate retry delay with exponential backoff and jitter."""
        # If server sent Retry-After, respect it
        if resp and resp.status_code == 429:
            retry_after = _parse_retry_after(resp)
            if retry_after:
                return retry_after

        # Exponential backoff: 2^attempt seconds (2, 4, 8...)
        # Add jitter to prevent thundering herd
        import random
        base_delay = 2 ** attempt
        jitter = random.uniform(0, 0.5 * base_delay)
        return base_delay + jitter

    def tiers(self) -> dict[str, list[str]]:
        """Return the services available per tier, as reported by the API.

        This endpoint is public and reflects the live server configuration.
        Use it to discover valid tier names and which services each tier runs.

        Returns:
            Dict mapping tier name to list of service names, e.g.::

                {
                    "basic":   ["colors", "content_analysis", "metadata", "nsfw2", ...],
                    "premium": ["blip", "caption_summary", "colors", "face", ...],
                }
        """
        url = f"{self._base_url}/tiers"
        logger.debug("GET /tiers")

        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.get(url)

                if resp.status_code == 200:
                    logger.debug("GET /tiers -> 200 OK")
                    return resp.json()["tiers"]

                # Check if we should retry this error
                if attempt < self._max_retries and self._should_retry(None, resp):
                    delay = self._retry_delay(attempt, resp)
                    logger.warning(f"GET /tiers -> {resp.status_code}, retrying in {delay:.1f}s (attempt {attempt + 1}/{self._max_retries})")
                    time.sleep(delay)
                    continue

                # Non-retryable error or out of retries
                detail = _error_message(resp)
                msg = f"{resp.status_code}: {detail}" if detail else f"Unexpected status {resp.status_code} from /tiers"
                raise Ice9Error(msg)

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                # Check if we should retry
                if attempt < self._max_retries and self._should_retry(exc):
                    delay = self._retry_delay(attempt)
                    time.sleep(delay)
                    continue

                # Out of retries
                if isinstance(exc, httpx.ConnectError):
                    raise Ice9Error(f"Could not connect to the ice9 API at {self._base_url}") from exc
                else:
                    raise Ice9Error("Request to /tiers timed out") from None

    def services(self) -> list[str]:
        """Return the list of available services.

        This endpoint is public and reflects the configured service catalog.
        Use it to discover what services exist across all tiers.

        Returns:
            List of service names, e.g.::

                ["blip2", "colors", "florence2", "metadata", "nudenet", "yolo_v8", ...]
        """
        url = f"{self._base_url}/services"
        logger.debug("GET /services")

        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.get(url)

                if resp.status_code == 200:
                    logger.debug("GET /services -> 200 OK")
                    return resp.json()["services"]

                # Check if we should retry this error
                if attempt < self._max_retries and self._should_retry(None, resp):
                    delay = self._retry_delay(attempt, resp)
                    logger.warning(f"GET /services -> {resp.status_code}, retrying in {delay:.1f}s (attempt {attempt + 1}/{self._max_retries})")
                    time.sleep(delay)
                    continue

                # Non-retryable error or out of retries
                detail = _error_message(resp)
                msg = f"{resp.status_code}: {detail}" if detail else f"Unexpected status {resp.status_code} from /services"
                raise Ice9Error(msg)

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                # Check if we should retry
                if attempt < self._max_retries and self._should_retry(exc):
                    delay = self._retry_delay(attempt)
                    time.sleep(delay)
                    continue

                # Out of retries
                if isinstance(exc, httpx.ConnectError):
                    raise Ice9Error(f"Could not connect to the ice9 API at {self._base_url}") from exc
                else:
                    raise Ice9Error("Request to /services timed out") from None

    def get_result(self, image_id: int) -> AnalysisResult:
        """Retrieve results for a previously analyzed image.

        Args:
            image_id: The image ID returned from a previous analyze() call.

        Returns:
            AnalysisResult with the completed analysis.

        Raises:
            AuthError:      Invalid or missing API key.
            RateLimitError: Rate limit hit; check retry_after on the exception.
            Ice9Error:      Image not found or other API error.
        """
        url = f"{self._base_url}/results/{image_id}"

        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.get(url)

                # Non-retryable errors (always raise immediately)
                if resp.status_code == 401:
                    raise AuthError("Invalid or deactivated API key")
                if resp.status_code == 404:
                    raise Ice9Error(f"Image {image_id} not found")

                # Success
                if resp.status_code == 200:
                    return AnalysisResult._from_status(resp.json())

                # Retryable errors
                if attempt < self._max_retries and self._should_retry(None, resp):
                    delay = self._retry_delay(attempt, resp)
                    time.sleep(delay)
                    continue

                # Out of retries or non-retryable
                if resp.status_code == 429:
                    retry_after = _parse_retry_after(resp)
                    raise RateLimitError("Rate limit exceeded on /results", retry_after=retry_after)

                detail = _error_message(resp)
                msg = f"{resp.status_code}: {detail}" if detail else f"Unexpected status {resp.status_code} from /results"
                raise Ice9Error(msg)

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt < self._max_retries and self._should_retry(exc):
                    delay = self._retry_delay(attempt)
                    time.sleep(delay)
                    continue

                if isinstance(exc, httpx.ConnectError):
                    raise Ice9Error(f"Could not connect to the ice9 API at {self._base_url}") from exc
                else:
                    raise Ice9Error("Request to /results timed out") from None

    def get_status(self, image_id: int) -> dict:
        """Get current analysis status for manual polling.

        This method returns the raw /status response, useful for implementing
        custom polling loops or progress tracking. For most use cases, prefer
        analyze(stream=True) which handles real-time updates automatically.

        Args:
            image_id: The image ID returned from a previous analyze() call.

        Returns:
            Dict with current analysis state, including:
            - is_complete: bool indicating if analysis finished
            - services_submitted: list of service names
            - service_results: dict of results for completed services
            - services_failed: dict of failed services (if any)
            - *_complete: various completion flags for downstream services

        Raises:
            AuthError:      Invalid or missing API key.
            RateLimitError: Rate limit hit; check retry_after on the exception.
            Ice9Error:      Image not found or other API error.

        Example:
            # Manual polling loop (only use if streaming isn't available)
            while True:
                status = client.get_status(image_id)
                print(f"Progress: {status.get('services_completed', {})}")
                if status['is_complete']:
                    break
                time.sleep(0.5)
        """
        url = f"{self._base_url}/status/{image_id}"

        for attempt in range(self._max_retries + 1):
            try:
                resp = self._client.get(url)

                # Non-retryable errors (always raise immediately)
                if resp.status_code == 401:
                    raise AuthError("Invalid or deactivated API key")
                if resp.status_code == 404:
                    raise Ice9Error(f"Image {image_id} not found")

                # Success
                if resp.status_code == 200:
                    return resp.json()

                # Retryable errors
                if attempt < self._max_retries and self._should_retry(None, resp):
                    delay = self._retry_delay(attempt, resp)
                    time.sleep(delay)
                    continue

                # Out of retries or non-retryable
                if resp.status_code == 429:
                    retry_after = _parse_retry_after(resp)
                    raise RateLimitError("Rate limit exceeded on /status", retry_after=retry_after)

                detail = _error_message(resp)
                msg = f"{resp.status_code}: {detail}" if detail else f"Unexpected status {resp.status_code} from /status"
                raise Ice9Error(msg)

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt < self._max_retries and self._should_retry(exc):
                    delay = self._retry_delay(attempt)
                    time.sleep(delay)
                    continue

                if isinstance(exc, httpx.ConnectError):
                    raise Ice9Error(f"Could not connect to the ice9 API at {self._base_url}") from exc
                else:
                    raise Ice9Error("Request to /status timed out") from None

    def analyze(
        self,
        image: str | Path | BinaryIO,
        *,
        tier: str | None = None,
        image_group: str = "api",
        timeout: float | None = None,
        stream: bool = False,
        raise_on_partial: bool = True,
    ):
        """Submit an image for analysis and return results.

        Args:
            image:            Path to an image file (str or Path), or an open binary
                              file object.
            tier:             Processing tier. If omitted, the SDK uses the
                              baseline tier (currently ``"basic"``). Higher tiers
                              must be requested explicitly. Use client.tiers()
                              to see what is available.
            image_group:      Tag for grouping images server-side. Defaults to 'api'.
            timeout:          Maximum seconds to wait for completion. Defaults to the
                              client's default_timeout.
            stream:           If True, return a generator that yields a partial
                              AnalysisResult each time a service completes, followed
                              by the final complete result. If False (default), block
                              until all services are done and return the full result.
            raise_on_partial: If True (default), raise PartialResultError when some
                              services fail. If False, return the result with
                              services_failed populated and log a warning.

        Returns:
            AnalysisResult (blocking) or generator of AnalysisResult (streaming).
            Each streaming yield has the same type; check ``result.is_complete``
            to identify the final yield.

        Raises:
            AuthError:            Invalid or missing API key.
            ImageRejectedError:   Server rejected the image or unknown tier.
            RateLimitError:       Rate limit hit; check retry_after on the exception.
            AnalysisTimeoutError: Analysis did not complete within the timeout.
            PartialResultError:   Completed but some services failed (only when
                                  raise_on_partial=True); result is on the
                                  exception's .result attribute.
            Ice9Error:            Any other API error.
        """
        effective_timeout = timeout if timeout is not None else self._default_timeout
        deadline = time.monotonic() + effective_timeout
        tier = tier or BASELINE_TIER

        image_id = self._upload(image, tier, image_group)

        if stream:
            return self._stream(image_id, deadline, raise_on_partial)

        self._poll(image_id, deadline)
        result = self.get_result(image_id)

        return self._handle_partial_result(result, raise_on_partial)

    def _handle_partial_result(
        self,
        result: AnalysisResult,
        raise_on_partial: bool,
    ) -> AnalysisResult:
        """Raise or log if the final result contains failed services."""

        if result.services_failed:
            if raise_on_partial:
                raise PartialResultError(
                    f"Analysis completed with failed services: "
                    f"{list(result.services_failed.keys())}",
                    result=result,
                )
            else:
                logger.warning(
                    f"Analysis completed with failed services: "
                    f"{list(result.services_failed.keys())}"
                )

        return result

    def _merge_stream_accumulated_results(
        self,
        result: AnalysisResult,
        accumulated: dict,
    ) -> AnalysisResult:
        """Preserve already-observed stream completions if /results briefly lags."""
        if not accumulated:
            return result

        raw = dict(result._raw)
        merged_service_results = dict(raw.get("service_results") or {})
        changed = False

        for service, entry in accumulated.items():
            if service not in merged_service_results:
                merged_service_results[service] = entry
                changed = True

        merged_services_submitted = list(raw.get("services_submitted") or [])
        for service in accumulated:
            if service not in merged_services_submitted:
                merged_services_submitted.append(service)
                changed = True

        if not changed:
            return result

        raw["service_results"] = merged_service_results
        raw["services_submitted"] = merged_services_submitted
        return AnalysisResult._from_status(raw)

    def _finalize_stream_result(
        self,
        image_id: int,
        accumulated: dict,
    ) -> AnalysisResult:
        """Fetch the canonical final result after a terminal SSE complete event."""
        final = self.get_result(image_id)
        return self._merge_stream_accumulated_results(final, accumulated)

    def _upload(self, image: str | Path | BinaryIO, tier: str | None, image_group: str) -> int:
        if isinstance(image, (str, Path)):
            image_str = str(image)
            # Check if it's a URL
            if image_str.startswith(("http://", "https://")):
                return self._upload_from_url(image_str, tier, image_group)
            else:
                # Local file path
                path = Path(image)
                with path.open("rb") as f:
                    return self._post_file(f, path.name, tier, image_group)
        else:
            name = getattr(image, "name", "upload.jpg")
            return self._post_file(image, name, tier, image_group)

    def _upload_from_url(self, url: str, tier: str | None, image_group: str) -> int:
        """Download an image from a URL and upload it to the API."""
        try:
            # Download the image with streaming to handle large files
            with self._client.stream("GET", url) as resp:
                if resp.status_code == 404:
                    raise ImageRejectedError(f"Image not found at URL: {url}")
                if resp.status_code != 200:
                    raise ImageRejectedError(
                        f"Failed to download image from URL (HTTP {resp.status_code}): {url}"
                    )

                # Check content type
                content_type = resp.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    raise ImageRejectedError(
                        f"URL does not point to an image (content-type: {content_type}): {url}"
                    )

                # Download to memory with size limit (10MB)
                max_size = 10 * 1024 * 1024  # 10MB
                chunks = []
                total_size = 0

                for chunk in resp.iter_bytes(chunk_size=8192):
                    total_size += len(chunk)
                    if total_size > max_size:
                        raise ImageRejectedError(f"Image at URL exceeds 10MB limit: {url}")
                    chunks.append(chunk)

                image_bytes = b"".join(chunks)

        except httpx.ConnectError as exc:
            raise ImageRejectedError(f"Could not connect to URL: {url}") from exc
        except httpx.TimeoutException:
            raise ImageRejectedError(f"Timeout downloading image from URL: {url}") from None

        # Extract filename from URL or use default
        filename = url.split("/")[-1].split("?")[0] or "download.jpg"
        if not any(filename.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
            filename = "download.jpg"

        # Upload the downloaded image
        fileobj = io.BytesIO(image_bytes)
        return self._post_file(fileobj, filename, tier, image_group)

    def _post_file(self, fileobj: BinaryIO, filename: str, tier: str | None, image_group: str) -> int:
        url = f"{self._base_url}/analyze"
        form_data: dict = {"image_group": image_group}
        form_data["tier"] = tier

        logger.debug(f"POST /analyze (tier={tier}, file={filename})")

        try:
            resp = self._client.post(
                url,
                files={"file": (filename, fileobj, "image/jpeg")},
                data=form_data,
            )
        except httpx.ConnectError as exc:
            raise Ice9Error(f"Could not connect to the ice9 API at {self._base_url}") from exc
        except httpx.TimeoutException:
            raise Ice9Error("Request to /analyze timed out") from None

        if resp.status_code == 401:
            raise AuthError("Invalid or deactivated API key")
        if resp.status_code == 429:
            retry_after = _parse_retry_after(resp)
            raise RateLimitError("Rate limit exceeded on /analyze", retry_after=retry_after)
        if resp.status_code == 400:
            msg = _error_message(resp) or "Image rejected by server"
            raise ImageRejectedError(msg)
        if resp.status_code != 202:
            detail = _error_message(resp)
            msg = f"{resp.status_code}: {detail}" if detail else f"Unexpected status {resp.status_code} from /analyze"
            raise Ice9Error(msg)

        body = resp.json()
        image_id = body["image_id"]
        logger.info(f"POST /analyze -> 202 Accepted (image_id={image_id})")
        return image_id

    def _poll(self, image_id: int, deadline: float) -> dict:
        url = f"{self._base_url}/status/{image_id}"
        consecutive_errors = 0
        max_consecutive_errors = 2  # Fail fast if status keeps failing

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AnalysisTimeoutError(
                    f"Analysis of image {image_id} did not complete within the timeout"
                )

            try:
                resp = self._client.get(url)
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                # Connection/timeout errors during polling - retry briefly
                consecutive_errors += 1
                if consecutive_errors > max_consecutive_errors:
                    if isinstance(exc, httpx.ConnectError):
                        raise Ice9Error(f"Lost connection to ice9 API while polling") from exc
                    else:
                        raise Ice9Error("Request to /status timed out") from None
                # Wait and retry
                time.sleep(min(2.0, remaining))
                continue

            # Non-retryable errors
            if resp.status_code == 401:
                raise AuthError("Invalid or deactivated API key")
            if resp.status_code == 404:
                raise Ice9Error(f"Image {image_id} not found")

            # Rate limit - built-in retry
            if resp.status_code == 429:
                consecutive_errors = 0  # Reset on expected error
                retry_after = _parse_retry_after(resp) or self.POLL_INTERVAL
                time.sleep(min(retry_after, remaining))
                continue

            # 5xx errors - limited retry (status endpoint should never fail)
            if 500 <= resp.status_code < 600:
                consecutive_errors += 1
                if consecutive_errors > max_consecutive_errors:
                    raise Ice9Error(
                        f"API appears to be down (HTTP {resp.status_code} from /status). "
                        "Please try again later."
                    )
                # Wait briefly and retry
                time.sleep(min(2.0, remaining))
                continue

            # Success
            if resp.status_code == 200:
                consecutive_errors = 0  # Reset on success
                body = resp.json()
                if body.get("is_complete"):
                    logger.info(f"GET /status/{image_id} -> complete")
                    return body
                # Not complete yet - keep polling
                progress = body.get("progress", "?")
                logger.debug(f"GET /status/{image_id} -> in progress ({progress})")
                time.sleep(min(self.POLL_INTERVAL, max(0, deadline - time.monotonic())))
                continue

            # Other errors
            detail = _error_message(resp)
            msg = f"{resp.status_code}: {detail}" if detail else f"Unexpected status {resp.status_code} from /status"
            raise Ice9Error(msg)

    def _stream(self, image_id: int, deadline: float, raise_on_partial: bool = True):
        url = f"{self._base_url}/stream/{image_id}"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AnalysisTimeoutError(
                f"Analysis of image {image_id} did not complete within the timeout"
            )

        try:
            with self._client.stream(
                "GET",
                url,
                headers={"Accept": "text/event-stream"},
                timeout=httpx.Timeout(10, read=remaining + 10),  # +10s headroom
            ) as resp:
                if resp.status_code == 401:
                    raise AuthError("Invalid or deactivated API key")
                if resp.status_code == 404:
                    raise Ice9Error(f"Image {image_id} not found")
                if resp.status_code != 200:
                    detail = _error_message(resp)
                    msg = f"{resp.status_code}: {detail}" if detail else f"Unexpected status {resp.status_code} from /stream"
                    raise Ice9Error(msg)

                accumulated = {}
                current_event = None
                current_data = None

                for line in resp.iter_lines():
                    if line == "":
                        # Blank line — dispatch the buffered event
                        if current_event and current_data is not None:
                            try:
                                payload = json.loads(current_data)
                            except json.JSONDecodeError:
                                pass
                            else:
                                if current_event == "service_complete":
                                    service = payload["service"]
                                    result = payload["result"]
                                    result_data = result.get('data') if 'data' in result else result
                                    cluster_id = result_data.get('cluster_id') if isinstance(result_data, dict) else None
                                    if cluster_id is not None:
                                        # Multi-cluster service (e.g. colors_post): merge
                                        # predictions with cluster_id embedded in each entry.
                                        new_preds = [{**p, 'cluster_id': cluster_id}
                                                     for p in (result_data.get('predictions') or [])]
                                        existing = accumulated.get(service, {})
                                        accumulated[service] = {
                                            'predictions': (existing.get('predictions') or []) + new_preds
                                        }
                                    else:
                                        accumulated[service] = result
                                    yield AnalysisResult._from_partial(image_id, accumulated)
                                elif current_event == "complete":
                                    final = self._finalize_stream_result(image_id, accumulated)
                                    yield self._handle_partial_result(final, raise_on_partial)
                                    return
                                elif current_event == "timeout":
                                    raise AnalysisTimeoutError(
                                        f"Analysis of image {image_id} did not complete within the timeout"
                                    )
                        current_event = None
                        current_data = None
                        continue

                    if line.startswith(":"):
                        continue  # keepalive comment

                    if line.startswith("event:"):
                        current_event = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        current_data = line[len("data:"):].strip()

        except httpx.ConnectError as exc:
            raise Ice9Error(f"Could not connect to the ice9 API at {self._base_url}") from exc
        except httpx.TimeoutException:
            raise AnalysisTimeoutError(
                f"Analysis of image {image_id} did not complete within the timeout"
            ) from None


def _parse_retry_after(resp: httpx.Response) -> float | None:
    value = resp.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _error_message(resp: httpx.Response) -> str | None:
    try:
        data = resp.json()
        return data.get("error") or data.get("detail")
    except Exception:
        return None
