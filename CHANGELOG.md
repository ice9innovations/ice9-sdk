# Changelog

All notable changes to the ice9 SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
(loosely, while in 0.x).

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
