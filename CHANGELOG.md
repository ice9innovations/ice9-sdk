# Changelog

All notable changes to the ice9 SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
(loosely, while in 0.x).

## [0.0.15] - 2026-03-26

### Fixed
- Streaming finalization in both `Ice9` and `AsyncIce9` now treats `/status` as an additional source of truth after a stream `complete` event
  - Missing downstream services already materialized on `/status` are merged into the final `AnalysisResult`
  - If `/status` shows completed downstream services but `/results` is still stale, the SDK now retries `/results` briefly within a bounded grace window
- Added sync and async regressions for the stale-final `/results` race seen after downstream completion

## [0.0.14] - 2026-03-25

### Changed
- Final `analyze()` results now use `/results/<image_id>` as the canonical payload after `/status` reports `is_complete=true`
  - Both `Ice9` and `AsyncIce9` now treat `/status` as the completion gate and `/results` as the final result source
  - Prevents incomplete final `AnalysisResult` objects when `/status` completion briefly gets ahead of final result shaping

### Fixed
- Streaming finalization now preserves already-observed `service_complete` results if the immediate `/results` fetch briefly lags behind the stream
  - The final streamed `AnalysisResult` remains monotonic instead of dropping services the client already saw complete
- Terminal failed result artifacts with `data: null` now preserve `status` and `error_message`
  - Failed services returned as real result rows no longer collapse to empty payloads in the SDK model layer
- Basic-tier live integration now prefers a real local fixture image when available
  - Avoids exercising pose/face/grounding flows against a synthetic blank image by default

## [0.0.13] - 2026-03-24

### Fixed
- `result.censor()` now treats NudeNet bounding boxes as already being in original-image space
  - Removed the old client-side `_API_MAX_DIMENSION` compensation logic
  - Prevents double-scaling censor regions after the API coordinate-space normalization change

## [0.0.12] - 2026-03-23

### Added
- Real-API integration coverage for `services()`, `get_status()`, `get_result()`, SSE streaming, and async-client parity
- Explicit compatibility fixture for the current API `status`/`results` shape, including aggregate services and tolerated progress/dispatch fields

### Changed
- Integration test configuration now accepts either `ICE9_API_KEY` / `ICE9_BASE_URL` or `API_KEY` / `API_URL` from `.env`
- README now documents the supported public SDK surface and clarifies that internal operator endpoints are not part of the public compatibility contract

### Fixed
- Streaming final results now preserve `services_submitted` when the final SSE `complete` event omits that field
  - Both sync and async clients merge accumulated streamed services into the final `AnalysisResult`
  - Prevents empty or incomplete `result.services_submitted` on the final streaming yield

## [0.0.11] - 2026-03-23

### Added
- `Ice9` sync client now supports context manager (`with Ice9(...) as client`)
- Error messages now surface `detail` field from API responses in addition to `error`

### Fixed
- `AsyncIce9.aclose()` now sets `_client = None` after closing, preventing double-close
- `AsyncIce9.__aexit__` delegates to `aclose()` instead of duplicating close logic

## [0.0.10] - 2026-03-15

### Removed
- `result.caption_scores` — CLIP caption scoring has been removed from the backend
  - The `caption_score_*` postprocessing service is discontinued
  - `result.caption_scores` will always be `None` going forward

## [0.0.9] - 2026-03-13

### Fixed
- `caption_score_*` streaming events no longer surface as individual services in partial results
  - Previously: `result.to_dict()["services"]` included `caption_score_blip`, etc. as raw keys
  - Now: aggregated into `caption_scores` at accumulation time in `_stream()`, consistent with `_from_status`

## [0.0.8] - 2026-03-13

### Fixed
- Multi-cluster postprocessing services (e.g. `colors_post`) now correctly accumulate
  all clusters rather than overwriting with the last one
  - `_from_status`: embeds `cluster_id` into each prediction when aggregating multi-entry
    postprocessing services, so the UI can associate palettes with their source bounding box
  - Streaming: `service_complete` events for cluster services merge predictions instead of
    overwriting — result shape matches the polled path

## [0.0.7] - 2026-03-13

### Added
- `result.image_filename` — original filename of the uploaded image, as a first-class attribute
- `result.image_created` — ISO 8601 timestamp when the image record was created, as a first-class attribute
  - Both fields are `None` for partial streaming results (not available until the `complete` event)
- `caption_scores` aggregation now works in streaming mode
  - Partial `AnalysisResult` objects yielded during SSE streaming now include `result.caption_scores`
    as individual `caption_score_*` events arrive, consistent with the final polled result

### Changed
- `image_group` removed from `to_dict()` output — internal batching field, not user-facing
  - Still accessible via `result._raw["image_group"]` for anything that needs it

## [0.0.6] - 2026-03-13

### Added
- `result.rembg` — background removal matte, injected from top-level API response
  - Fields: `png_b64` (base64 grayscale PNG), `shape` ([height, width]), `model`, `premasked`
  - `result.rembg` is `None` when the service did not run
- `result.caption_scores` — aggregated CLIP similarity scores for all VLM captions
  - Scores arrive as individual `caption_score_*` entries in the `postprocessing` array
  - SDK aggregates them into a single `ServiceResult`: `result.caption_scores.blip`, `result.caption_scores.moondream`, etc.
  - Individual `caption_score_*` entries are not exposed directly
  - `result.caption_scores` is `None` when no caption scores are present (e.g. free tier)
- `grounding_validated` flag on noun consensus entries
  - Each noun in `result.noun_consensus.nouns` now includes `grounding_validated: bool`
  - Set by the windmill pipeline when a grounding service confirms the noun with a bounding box
  - SDK passes the field through from the API response

### Fixed
- Services returned in the `postprocessing` array now surface correctly via attribute access
  - Previously: `result.face`, `result.pose`, `result.caption_score_*`, etc. all returned `None`
  - Now: injected into `service_results` alongside primary services at result build time
  - Multiple entries for the same service (e.g. one face cluster per detected person) are aggregated — predictions are merged into a single list
  - Does not overwrite existing `service_results` entries (primary service always wins)

## [0.0.5] - 2026-03-12

### Fixed
- httpx client now respects user-provided timeout for uploads and reads
  - Previously: hardcoded 10s timeout caused large file uploads to fail regardless of configured timeout
  - Now: connect timeout stays 10s (fail fast if unreachable), read/write timeouts use the configured value
  - Affects both `Ice9` and `AsyncIce9`
- Streaming timeout is now a true inactivity timeout, not a wall-clock limit
  - Previously: deadline was set before upload, so slow uploads reduced streaming time
  - Now: timeout resets each time any data is received from the stream
  - An active stream producing results will never be cut off by elapsed time
  - Timeout only fires if no data arrives for the configured duration
  - Error message now distinguishes stream stall from analysis timeout

## [0.0.4] - 2026-03-12

### Added
- `get_status(image_id)` method for manual polling of analysis progress
  - Returns raw `/status` endpoint response with all fields preserved
  - Useful for custom polling loops when streaming isn't available
  - Both sync (`Ice9`) and async (`AsyncIce9`) clients support it

### Changed
- Updated documentation to emphasize streaming as primary pattern for real-time UIs
  - Added "Real-time Progress Updates" section with streaming and polling examples
  - Clarified when to use streaming vs polling
  - Added deployment guidance for async workers with SSE

### Context
This release clarifies SDK usage patterns after demo UI integration revealed a communication gap. The SDK was correctly designed around streaming (SSE) for real-time progress, but the demo UI was built with polling due to incorrect assumptions about SSE blocking workers. The `get_status()` method is now available as a fallback for environments where streaming isn't feasible, but streaming remains the recommended approach.

## [0.0.3] - 2026-03-12

### Changed
- Make `AsyncIce9` more discoverable by promoting it to first-class export
  - Added `AsyncIce9` directly to `__all__` (no longer lazy-loaded)
  - Shows up in autocomplete and documentation tools
- Improved async documentation in README
  - Quickstart now shows both sync and async examples side-by-side
  - Added "when to use async" guidance (web servers, bots, concurrent processing)
  - Clarifies async is not just available, but recommended for certain use cases
- Updated timing documentation based on real benchmarks
  - Free tier: "under a second (P50: 0.5s, P90: 5.6s)"
  - Basic tier: "8-10 seconds (P50: 7.6s, P95: 34s)" with 45s timeout
  - Premium tier: "13-16s benchmarks" with 60s timeout (conservative)
  - README timeout examples now use realistic values (45s instead of 120s)
- Added documentation for `to_dict()` serialization
  - Explains how `to_dict()` cleans up the structure (services nesting, strips metadata)
  - Shows example output structure
  - Positions `._raw` as escape hatch, not recommended usage (if you need it, the SDK should be improved)
- Added Support section to README with clear channels for issues, documentation, and feedback

### Fixed
- Corrected overly pessimistic timing claims in examples
  - basic_tier.py: Changed "up to 2 minutes" → "typically 8-10 seconds"
  - premium_tier.py: Changed "up to 3 minutes" → "13-16 seconds"
  - Timeout values adjusted to match actual API performance

## [0.0.2] - 2026-03-12

### Added
- `raise_on_partial` parameter to `analyze()` method in both `Ice9` and `AsyncIce9` clients
  - When set to `False`, partial results are returned instead of raising `PartialResultError`
  - Logs a warning when services fail
  - Works in both polling mode and streaming mode (`stream=True`)
  - Default is `True` to maintain backward compatibility

### Changed
- Error handling documentation in README now includes examples of `raise_on_partial=False`

## [0.0.1] - 2026-03-07

### Added
- Initial release of the ice9 SDK
- Synchronous `Ice9` client
- Asynchronous `AsyncIce9` client
- Support for multiple tiers (free, basic, premium, batch)
- SSE streaming mode for real-time progress updates
- URL support (SDK downloads images before submitting)
- Automatic retry logic with exponential backoff
- Result retrieval for previously analyzed images
- Image censoring via NudeNet detections
- Comprehensive test suite (unit + integration)
- Examples for all major features
- Full documentation in README
