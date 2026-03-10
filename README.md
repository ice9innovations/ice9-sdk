# ice9 SDK

[![PyPI version](https://badge.fury.io/py/ice9.svg)](https://badge.fury.io/py/ice9)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Python SDK for the [ice9](https://ice9.ai) image analysis API.

## Installation

```bash
pip install ice9
```

## Quickstart

```python
from ice9 import Ice9

client = Ice9(api_key="ice9_...")
result = client.analyze("photo.jpg")

print(result.nudenet)   # content moderation
print(result.colors)    # dominant colors
print(result.metadata)  # EXIF and file info
```

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

For async frameworks (FastAPI, aiohttp, Discord.py), use `AsyncIce9`:

```python
from ice9 import AsyncIce9

async with AsyncIce9() as client:
    result = await client.analyze("photo.jpg")
    print(result.nudenet)
```

All methods have async equivalents: `await client.analyze()`, `await client.get_result()`, `await client.tiers()`, `await client.services()`.

Streaming works with async generators:

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
result.nudenet.detections
result.colors.dominant
result.yolo_v8.boxes
```

Accessing a service that didn't run returns `None`. The raw API response is
available at `result._raw` if you need fields the SDK doesn't surface directly.

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

## Timeout and retries

The default timeout is 30 seconds. The SDK automatically retries transient errors (rate limits, 5xx, connection errors) up to 3 times with exponential backoff.

```python
# Configure timeout and retries
client = Ice9(
    api_key="ice9_...",
    timeout=120,        # seconds to wait for analysis
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
