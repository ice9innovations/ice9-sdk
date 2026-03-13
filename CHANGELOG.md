# Changelog

All notable changes to the ice9 SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
(loosely, while in 0.x).

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
