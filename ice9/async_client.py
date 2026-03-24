from __future__ import annotations

import io
import json
import logging
import os
import time
from pathlib import Path
from typing import AsyncIterator, BinaryIO

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


class AsyncIce9:
    """Async client for the ice9 image analysis API.

    Usage::

        from ice9 import AsyncIce9

        async with AsyncIce9(api_key="ice9_...") as client:
            result = await client.analyze("photo.jpg")
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
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            headers={"X-API-Key": self._api_key},
            timeout=httpx.Timeout(
                connect=10.0,
                read=self._default_timeout,
                write=self._default_timeout,
                pool=5.0,
            ),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.aclose()

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the httpx client."""
        if self._client is None:
            # Auto-create if not using context manager
            self._client = httpx.AsyncClient(
                headers={"X-API-Key": self._api_key},
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=self._default_timeout,
                    write=self._default_timeout,
                    pool=5.0,
                ),
            )
        return self._client

    def _should_retry(self, exc: Exception, resp: httpx.Response | None = None) -> bool:
        """Determine if a request should be retried based on the error."""
        if isinstance(exc, httpx.ConnectError):
            return True
        if isinstance(exc, httpx.TimeoutException):
            return True
        if resp and 500 <= resp.status_code < 600:
            return True
        if resp and resp.status_code == 429:
            return True
        return False

    def _retry_delay(self, attempt: int, resp: httpx.Response | None = None) -> float:
        """Calculate retry delay with exponential backoff and jitter."""
        if resp and resp.status_code == 429:
            retry_after = _parse_retry_after(resp)
            if retry_after:
                return retry_after

        import random
        base_delay = 2 ** attempt
        jitter = random.uniform(0, 0.5 * base_delay)
        return base_delay + jitter

    async def tiers(self) -> dict[str, list[str]]:
        """Return the services available per tier, as reported by the API.

        This endpoint is public and reflects the live server configuration.
        Use it to discover valid tier names and which services each tier runs.

        Returns:
            Dict mapping tier name to list of service names, e.g.::

                {
                    "free":     ["colors", "metadata", "nudenet", "ocr", "qr"],
                    "premium":  ["colors", "metadata", "nudenet", "ocr", "qr", "yolo", ...],
                }
        """
        url = f"{self._base_url}/tiers"
        client = self._get_client()
        logger.debug("GET /tiers")

        for attempt in range(self._max_retries + 1):
            try:
                resp = await client.get(url)

                if resp.status_code == 200:
                    logger.debug("GET /tiers -> 200 OK")
                    return resp.json()["tiers"]

                if attempt < self._max_retries and self._should_retry(None, resp):
                    delay = self._retry_delay(attempt, resp)
                    logger.warning(f"GET /tiers -> {resp.status_code}, retrying in {delay:.1f}s (attempt {attempt + 1}/{self._max_retries})")
                    await _async_sleep(delay)
                    continue

                detail = _error_message(resp)
                msg = f"{resp.status_code}: {detail}" if detail else f"Unexpected status {resp.status_code} from /tiers"
                raise Ice9Error(msg)

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt < self._max_retries and self._should_retry(exc):
                    delay = self._retry_delay(attempt)
                    await _async_sleep(delay)
                    continue

                if isinstance(exc, httpx.ConnectError):
                    raise Ice9Error(f"Could not connect to the ice9 API at {self._base_url}") from exc
                else:
                    raise Ice9Error("Request to /tiers timed out") from None

    async def services(self) -> list[str]:
        """Return the list of available services.

        This endpoint is public and reflects the configured service catalog.
        Use it to discover what services exist across all tiers.

        Returns:
            List of service names, e.g.::

                ["blip2", "colors", "florence2", "metadata", "nudenet", "yolo_v8", ...]
        """
        url = f"{self._base_url}/services"
        client = self._get_client()
        logger.debug("GET /services")

        for attempt in range(self._max_retries + 1):
            try:
                resp = await client.get(url)

                if resp.status_code == 200:
                    logger.debug("GET /services -> 200 OK")
                    return resp.json()["services"]

                if attempt < self._max_retries and self._should_retry(None, resp):
                    delay = self._retry_delay(attempt, resp)
                    logger.warning(f"GET /services -> {resp.status_code}, retrying in {delay:.1f}s (attempt {attempt + 1}/{self._max_retries})")
                    await _async_sleep(delay)
                    continue

                detail = _error_message(resp)
                msg = f"{resp.status_code}: {detail}" if detail else f"Unexpected status {resp.status_code} from /services"
                raise Ice9Error(msg)

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt < self._max_retries and self._should_retry(exc):
                    delay = self._retry_delay(attempt)
                    await _async_sleep(delay)
                    continue

                if isinstance(exc, httpx.ConnectError):
                    raise Ice9Error(f"Could not connect to the ice9 API at {self._base_url}") from exc
                else:
                    raise Ice9Error("Request to /services timed out") from None

    async def get_result(self, image_id: int) -> AnalysisResult:
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
        client = self._get_client()

        for attempt in range(self._max_retries + 1):
            try:
                resp = await client.get(url)

                if resp.status_code == 401:
                    raise AuthError("Invalid or deactivated API key")
                if resp.status_code == 404:
                    raise Ice9Error(f"Image {image_id} not found")

                if resp.status_code == 200:
                    return AnalysisResult._from_status(resp.json())

                if attempt < self._max_retries and self._should_retry(None, resp):
                    delay = self._retry_delay(attempt, resp)
                    await _async_sleep(delay)
                    continue

                if resp.status_code == 429:
                    retry_after = _parse_retry_after(resp)
                    raise RateLimitError("Rate limit exceeded on /results", retry_after=retry_after)

                detail = _error_message(resp)
                msg = f"{resp.status_code}: {detail}" if detail else f"Unexpected status {resp.status_code} from /results"
                raise Ice9Error(msg)

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt < self._max_retries and self._should_retry(exc):
                    delay = self._retry_delay(attempt)
                    await _async_sleep(delay)
                    continue

                if isinstance(exc, httpx.ConnectError):
                    raise Ice9Error(f"Could not connect to the ice9 API at {self._base_url}") from exc
                else:
                    raise Ice9Error("Request to /results timed out") from None

    async def get_status(self, image_id: int) -> dict:
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
                status = await client.get_status(image_id)
                print(f"Progress: {status.get('services_completed', {})}")
                if status['is_complete']:
                    break
                await asyncio.sleep(0.5)
        """
        url = f"{self._base_url}/status/{image_id}"
        client = self._get_client()

        for attempt in range(self._max_retries + 1):
            try:
                resp = await client.get(url)

                if resp.status_code == 401:
                    raise AuthError("Invalid or deactivated API key")
                if resp.status_code == 404:
                    raise Ice9Error(f"Image {image_id} not found")

                if resp.status_code == 200:
                    return resp.json()

                if attempt < self._max_retries and self._should_retry(None, resp):
                    delay = self._retry_delay(attempt, resp)
                    await _async_sleep(delay)
                    continue

                if resp.status_code == 429:
                    retry_after = _parse_retry_after(resp)
                    raise RateLimitError("Rate limit exceeded on /status", retry_after=retry_after)

                detail = _error_message(resp)
                msg = f"{resp.status_code}: {detail}" if detail else f"Unexpected status {resp.status_code} from /status"
                raise Ice9Error(msg)

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if attempt < self._max_retries and self._should_retry(exc):
                    delay = self._retry_delay(attempt)
                    await _async_sleep(delay)
                    continue

                if isinstance(exc, httpx.ConnectError):
                    raise Ice9Error(f"Could not connect to the ice9 API at {self._base_url}") from exc
                else:
                    raise Ice9Error("Request to /status timed out") from None

    async def analyze(
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
            tier:             Processing tier. If omitted, the server applies the
                              default for your API key. Use client.tiers() to see
                              what is available.
            image_group:      Tag for grouping images server-side. Defaults to 'api'.
            timeout:          Timeout in seconds. Defaults to the client's
                              default_timeout. Behavior differs by mode:
                              - Non-streaming: wall-clock deadline from the start
                                of analyze() (includes upload time).
                              - Streaming: inactivity timeout — resets each time
                                any data is received. An active stream that is
                                producing results will never be cut off regardless
                                of total elapsed time. Fires only if no data
                                arrives for this many seconds.
            stream:           If True, return an async generator that yields a partial
                              AnalysisResult each time a service completes, followed
                              by the final complete result. If False (default), block
                              until all services are done and return the full result.
            raise_on_partial: If True (default), raise PartialResultError when some
                              services fail. If False, return the result with
                              services_failed populated and log a warning.

        Returns:
            AnalysisResult (blocking) or async generator of AnalysisResult (streaming).
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

        image_id = await self._upload(image, tier, image_group)

        if stream:
            return self._stream(image_id, effective_timeout, raise_on_partial)

        status = await self._poll(image_id, deadline)
        result = AnalysisResult._from_status(status)

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

    async def _upload(self, image: str | Path | BinaryIO, tier: str | None, image_group: str) -> int:
        if isinstance(image, (str, Path)):
            image_str = str(image)
            # Check if it's a URL
            if image_str.startswith(("http://", "https://")):
                return await self._upload_from_url(image_str, tier, image_group)
            else:
                # Local file path
                path = Path(image)
                with path.open("rb") as f:
                    return await self._post_file(f, path.name, tier, image_group)
        else:
            name = getattr(image, "name", "upload.jpg")
            return await self._post_file(image, name, tier, image_group)

    async def _upload_from_url(self, url: str, tier: str | None, image_group: str) -> int:
        """Download an image from a URL and upload it to the API."""
        client = self._get_client()

        try:
            # Download the image with streaming to handle large files
            async with client.stream("GET", url) as resp:
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

                async for chunk in resp.aiter_bytes(chunk_size=8192):
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
        return await self._post_file(fileobj, filename, tier, image_group)

    async def _post_file(self, fileobj: BinaryIO, filename: str, tier: str | None, image_group: str) -> int:
        url = f"{self._base_url}/analyze"
        form_data: dict = {"image_group": image_group}
        if tier is not None:
            form_data["tier"] = tier

        client = self._get_client()
        logger.debug(f"POST /analyze (tier={tier or 'default'}, file={filename})")

        try:
            resp = await client.post(
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

    async def _poll(self, image_id: int, deadline: float) -> dict:
        url = f"{self._base_url}/status/{image_id}"
        client = self._get_client()
        consecutive_errors = 0
        max_consecutive_errors = 2

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AnalysisTimeoutError(
                    f"Analysis of image {image_id} did not complete within the timeout"
                )

            try:
                resp = await client.get(url)
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                consecutive_errors += 1
                if consecutive_errors > max_consecutive_errors:
                    if isinstance(exc, httpx.ConnectError):
                        raise Ice9Error(f"Lost connection to ice9 API while polling") from exc
                    else:
                        raise Ice9Error("Request to /status timed out") from None
                await _async_sleep(min(2.0, remaining))
                continue

            if resp.status_code == 401:
                raise AuthError("Invalid or deactivated API key")
            if resp.status_code == 404:
                raise Ice9Error(f"Image {image_id} not found")

            if resp.status_code == 429:
                consecutive_errors = 0
                retry_after = _parse_retry_after(resp) or self.POLL_INTERVAL
                await _async_sleep(min(retry_after, remaining))
                continue

            if 500 <= resp.status_code < 600:
                consecutive_errors += 1
                if consecutive_errors > max_consecutive_errors:
                    raise Ice9Error(
                        f"API appears to be down (HTTP {resp.status_code} from /status). "
                        "Please try again later."
                    )
                await _async_sleep(min(2.0, remaining))
                continue

            if resp.status_code == 200:
                consecutive_errors = 0
                body = resp.json()
                if body.get("is_complete"):
                    logger.info(f"GET /status/{image_id} -> complete")
                    return body
                # Still in progress
                services_submitted = body.get("services_submitted", [])
                services_complete = sum(1 for s in body.get("service_results", {}).values() if s.get("status") == "success")
                progress = f"{services_complete}/{len(services_submitted)} services"
                logger.debug(f"GET /status/{image_id} -> in progress ({progress})")
                await _async_sleep(min(self.POLL_INTERVAL, max(0, deadline - time.monotonic())))
                continue

            detail = _error_message(resp)
            msg = f"{resp.status_code}: {detail}" if detail else f"Unexpected status {resp.status_code} from /status"
            raise Ice9Error(msg)

    async def _stream(self, image_id: int, inactivity_timeout: float, raise_on_partial: bool = True) -> AsyncIterator[AnalysisResult]:
        """Stream analysis results using SSE.

        Uses a true inactivity timeout: the clock resets each time any data is
        received. A stream that is actively sending events will never be cut off
        regardless of total elapsed time. The timeout only fires if no data
        arrives for inactivity_timeout seconds.
        """
        import asyncio

        url = f"{self._base_url}/stream/{image_id}"
        client = self._get_client()

        try:
            async with client.stream(
                "GET",
                url,
                headers={"Accept": "text/event-stream"},
                timeout=httpx.Timeout(10, read=inactivity_timeout + 10),  # backstop
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

                aiter = resp.aiter_lines()
                while True:
                    try:
                        line = await asyncio.wait_for(
                            aiter.__anext__(),
                            timeout=inactivity_timeout,
                        )
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        raise AnalysisTimeoutError(
                            f"Stream for image {image_id} stalled — "
                            f"no data received for {inactivity_timeout:.0f}s"
                        ) from None

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
                                    final_payload = dict(payload)
                                    if accumulated:
                                        existing_results = final_payload.get("service_results") or {}
                                        final_payload["service_results"] = {
                                            **accumulated,
                                            **existing_results,
                                        }
                                        if not final_payload.get("services_submitted"):
                                            final_payload["services_submitted"] = list(accumulated.keys())
                                    final = AnalysisResult._from_status(final_payload)
                                    if final.services_failed:
                                        if raise_on_partial:
                                            raise PartialResultError(
                                                f"Analysis completed with failed services: "
                                                f"{list(final.services_failed.keys())}",
                                                result=final,
                                            )
                                        else:
                                            logger.warning(
                                                f"Analysis completed with failed services: "
                                                f"{list(final.services_failed.keys())}"
                                            )
                                    yield final
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

    async def aclose(self):
        """Close the underlying HTTP client. Only needed if not using context manager."""
        if self._client:
            await self._client.aclose()
            self._client = None


async def _async_sleep(seconds: float):
    """Sleep helper using asyncio."""
    import asyncio
    await asyncio.sleep(seconds)


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
