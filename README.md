# ice9 SDK

[![PyPI version](https://badge.fury.io/py/ice9.svg)](https://badge.fury.io/py/ice9)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Python SDK for the [ice9](https://ice9.ai) image analysis API.

## Stability

`ice9` is currently a pre-1.0 SDK and uses `0.0.x` versioning.

- Breaking changes may still happen between releases while the upstream API and
  pipeline contracts are settling
- New services are expected to appear over time without requiring SDK changes
- If you pin the SDK, read [CHANGELOG.md](./CHANGELOG.md) before upgrading

After 1.0, the SDK will follow semantic versioning more strictly.

## Installation

```bash
pip install ice9
```

## Quickstart

**Synchronous (scripts, notebooks):**
```python
from ice9 import Ice9

client = Ice9(api_key="ice9_...")
result = client.analyze("photo.jpg")

print(result.nudenet)   # content moderation
print(result.colors)    # dominant colors
print(result.metadata)  # EXIF and file info
```

**Asynchronous (FastAPI, Discord bots, async web apps):**
```python
from ice9 import AsyncIce9

async with AsyncIce9(api_key="ice9_...") as client:
    result = await client.analyze("photo.jpg")
    print(result.nudenet)
```

Both clients have identical APIs - just add `async`/`await` for the async version.

The SDK accepts images from multiple sources:

```python
# Local file path
result = client.analyze("photo.jpg")

# URL (SDK downloads it for you)
result = client.analyze("https://example.com/photo.jpg")

# File object
with open("photo.jpg", "rb") as f:
    result = client.analyze(f)
```

**Note:** URLs are downloaded by the SDK (up to 10MB) and then submitted to the API. The API itself does not store images.

## Authentication

Pass your API key directly or set the `ICE9_API_KEY` environment variable:

```bash
export ICE9_API_KEY=ice9_...
```

```python
client = Ice9()  # picks up ICE9_API_KEY automatically
```

## Async/Await

`AsyncIce9` is a fully async client perfect for web servers and bots. It doesn't block your event loop while waiting for analysis results, so one process can handle many concurrent requests efficiently.

**When to use async:**
- ✅ Web servers (FastAPI, Flask with async routes, aiohttp)
- ✅ Discord/Telegram bots
- ✅ Any async application processing multiple images concurrently
- ❌ Simple scripts or Jupyter notebooks (use sync `Ice9` instead)

All methods have async equivalents: `await client.analyze()`, `await client.get_result()`, `await client.tiers()`, `await client.services()`.

**Async streaming** for real-time progress updates:

```python
async for result in await client.analyze("photo.jpg", stream=True):
    if result.is_complete:
        print("Done!")
    else:
        print(f"Service {result.services_submitted[-1]} ready")
```

Both `Ice9` (sync) and `AsyncIce9` use the same underlying HTTP library (httpx), so there's no extra installation needed for async support.

## Tiers and Services

The API processes images at different tiers. Each tier runs a different set of
services. To see what's available:

```python
# See which services are in each tier
tiers = client.tiers()
# {
#   "free":    ["colors", "metadata", "nudenet"],
#   "basic":   ["blip", "colors", "florence2", ...],
#   "premium": [...],
# }

# Or get a list of all available services
services = client.services()
# ["blip2", "colors", "florence2", "metadata", "nudenet", "yolo_v8", ...]
```

Pass a tier to `analyze()`:

```python
result = client.analyze("photo.jpg", tier="basic")
```

If you omit `tier`, the server uses the default for your key.

## Results

Services that ran are accessible as attributes on the result:

```python
result.nudenet.detections        # content moderation
result.colors.dominant           # dominant colors
result.yolo_v8.predictions       # object detection
result.noun_consensus.nouns      # consensus nouns across all VLMs
result.rembg.png_b64             # background removal matte (base64 PNG)
```

Accessing a service that didn't run returns `None`.

Which services are present depends on your tier — use `client.tiers()` to see what's included. Higher tiers add VLM captioning services (blip, moondream, florence2, gemini, gpt_nano, haiku, ollama, qwen) and downstream analysis (noun_consensus, verb_consensus, caption_summary, rembg). These services surface automatically when they run — no SDK changes needed as the service lineup evolves.

### Serializing results

For passing results to other systems (web frontends, databases, etc.), use `to_dict()`:

```python
result.to_dict()
# {
#   "image_id": 123,
#   "services_submitted": ["colors", "nudenet"],
#   "services_failed": {},
#   "services": {
#     "colors": {
#       "dominant": ["#FF0000", "#00FF00"],
#       "palette": [...]
#     },
#     "nudenet": {
#       "detections": [...]
#     }
#   }
# }
```

The SDK cleans up the structure:
- Services are nested under `"services"` (prevents field name collisions with top-level metadata)
- Redundant `"service"` and `"status"` fields are stripped
- Service data is unwrapped (no extra `"data"` nesting)

**Note:** The raw API response is available at `result._raw`, but you shouldn't need it. If you find yourself reaching for `._raw`, that's a sign the SDK isn't surfacing something it should—please [open an issue](https://github.com/ice9innovations/ice9-sdk/issues).

## Retrieving past results

Results are stored and can be retrieved later using the image ID:

```python
# Initial analysis
result = client.analyze("photo.jpg")
image_id = result.image_id  # Save this

# Later, retrieve the same results
result = client.get_result(image_id)
```

This is useful for:
- Retrieving results across different sessions
- Avoiding re-analysis of the same image
- Building dashboards or reports from historical data

## SDK Scope

This SDK wraps the supported customer API surface:

- `POST /analyze`
- `GET /status/<image_id>`
- `GET /results/<image_id>`
- `GET /stream/<image_id>`
- `GET /tiers`
- `GET /services`

Internal operator endpoints such as `/internal/outbox` and
`/internal/outbox/retry` are not currently wrapped by the public SDK. Those
endpoints are operational controls rather than part of the stable customer
contract, so they may evolve without SDK compatibility guarantees.

## Real-time Progress Updates

For real-time UIs, dashboards, or monitoring tools that need to show analysis progress as it happens, use **streaming** (recommended) or manual polling (fallback).

### Streaming (Recommended)

The SDK handles SSE (Server-Sent Events) connections internally and yields partial results as services complete:

```python
# Synchronous
for result in client.analyze("photo.jpg", stream=True):
    # result.is_complete is False until final result
    completed = len([s for s in result.services_submitted if getattr(result, s)])
    print(f"Progress: {completed}/{len(result.services_submitted)} services")

    if result.is_complete:
        print("Analysis complete!")
        break

# Asynchronous
async for result in await client.analyze("photo.jpg", stream=True):
    update_dashboard(result)  # Update UI with partial results
    if result.is_complete:
        break
```

**Why streaming?** It's efficient, real-time, and doesn't require you to write polling loops. The SDK manages the connection and yields results as they arrive.

**Deployment note:** For web servers proxying SSE to browsers, use async workers (e.g., `gunicorn --worker-class gevent`) to handle many concurrent connections without blocking.

### Manual Polling (Fallback)

If streaming isn't available in your environment, use `get_status()` for manual polling:

```python
import time

# Submit analysis
result = client.analyze("photo.jpg")
image_id = result.image_id

# Or if you already have an image_id:
while True:
    status = client.get_status(image_id)
    print(f"Progress: {status.get('services_completed', {})}")

    if status['is_complete']:
        # Status dict has all fields from /status endpoint
        final_result = status
        break

    time.sleep(0.5)  # Poll every 500ms
```

**When to use polling:** Only when SSE isn't available (e.g., restrictive firewalls, legacy infrastructure). Streaming is preferred for most use cases.

## Error handling

```python
from ice9 import (
    Ice9Error,           # base — catch this for any SDK error
    AuthError,           # invalid or deactivated key
    ImageRejectedError,  # bad format, too large, empty
    RateLimitError,      # check .retry_after for backoff hint
    AnalysisTimeoutError,# didn't complete within timeout
    PartialResultError,  # completed, but some services failed
)

try:
    result = client.analyze("photo.jpg")
except PartialResultError as e:
    # Some services failed — the partial result is still accessible
    result = e.result
    print("Failed services:", result.services_failed)
except AnalysisTimeoutError:
    print("Timed out waiting for results")
except Ice9Error as e:
    print("API error:", e)
```

`PartialResultError` carries the partial result on `.result` so you can decide
whether what succeeded is enough for your use case.

### Handling partial results without exceptions

If partial results are acceptable for your use case (e.g., you only need nudenet and other services are optional), use `raise_on_partial=False`:

```python
# Returns result with services_failed populated, logs a warning instead of raising
result = client.analyze("photo.jpg", raise_on_partial=False)

if result.services_failed:
    print(f"Warning: some services failed: {result.services_failed}")

# Use the partial result
if result.nudenet:
    print("Nudenet succeeded:", result.nudenet.detections)
```

This is cleaner than catching `PartialResultError` when you know partial results are acceptable.

## Timeout and retries

The default timeout is 30 seconds, which is sufficient for most tiers (free: <1s, basic: ~8s, premium: ~13s). The SDK automatically retries transient errors (rate limits, 5xx, connection errors) up to 3 times with exponential backoff.

```python
# Configure timeout and retries
client = Ice9(
    api_key="ice9_...",
    timeout=45,         # seconds to wait for analysis (increase for batch tier)
    max_retries=3,      # number of retries (default: 3, set to 0 to disable)
)

# Per-call timeout override
result = client.analyze("photo.jpg", timeout=60)
```

**What gets retried:**
- ✅ Rate limits (429) - respects `Retry-After` header
- ✅ Server errors (5xx) - exponential backoff with jitter
- ✅ Connection errors - transient network issues
- ❌ Auth errors (401/403) - won't fix themselves
- ❌ Client errors (400/404) - won't fix themselves
- ❌ Initial `/analyze` submission - never retried (costs money + bandwidth)

The SDK retries reads (`tiers()`, `get_result()`, status polling) but never retries the initial image submission to protect against accidental charges.

## Batch processing

For high-volume batch workloads, use the **batch tier**:

```python
from concurrent.futures import ThreadPoolExecutor

def analyze_image(path):
    return client.analyze(path, tier="batch")

with ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(analyze_image, image_paths))
```

The batch tier is designed for parallel processing and uses LLM consensus (GPT, Gemini, Claude) for maximum accuracy. See `examples/batch_tier.py` for a complete example.

**Key differences:**
- **Batch tier**: Parallelization supported, LLM consensus, no NSFW support
- **Basic/Premium tiers**: Real-time optimized, single-image analysis, NSFW support

For pricing details, see [ice9.ai/pricing](https://ice9.ai/pricing).

## Logging

The SDK uses Python's standard `logging` module to log HTTP requests and responses. This can be helpful for debugging or monitoring API usage.

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("ice9").setLevel(logging.DEBUG)

# Now all SDK operations will log
client = Ice9()
result = client.analyze("photo.jpg")
```

**Log levels:**
- **DEBUG**: Every API call (GET /tiers, POST /analyze, polling GET /status)
- **INFO**: Successful submissions and completions
- **WARNING**: Retry attempts with backoff delays

Example output:
```
DEBUG:ice9:POST /analyze (tier=default, file=photo.jpg)
INFO:ice9:POST /analyze -> 202 Accepted (image_id=12345)
DEBUG:ice9:GET /status/12345 -> in progress (2/5 services)
DEBUG:ice9:GET /status/12345 -> in progress (4/5 services)
INFO:ice9:GET /status/12345 -> complete
```

**When to use:**
- Debugging failed requests or unexpected behavior
- Monitoring rate limit retries
- Tracking which services are taking longest
- Understanding retry/backoff patterns

By default, logging is **off** (only WARNING and above). Enable it explicitly when needed.

## Running the tests

Unit tests (no credentials required):

```bash
pip install ice9[dev]
pytest
```

Integration tests (requires `ICE9_API_KEY`):

```bash
export ICE9_API_KEY=ice9_...
pytest tests/integration/ -v
```

## Support

**Issues and feature requests:** [GitHub Issues](https://github.com/ice9innovations/ice9-sdk/issues)

**Documentation:** [ice9.ai/docs](https://ice9.ai/docs)

**Questions or feedback:** Visit [ice9.ai](https://ice9.ai) for contact information.

We're actively maintaining this SDK and respond to issues promptly. If something isn't working as expected or you'd like to see a feature added, please let us know.
