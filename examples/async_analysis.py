"""
Async example using AsyncIce9 for non-blocking image analysis.

This is useful for async frameworks like FastAPI, aiohttp, or Discord.py
where you want to avoid blocking the event loop.

Requirements:
    pip install ice9[async]

Usage:
    ICE9_API_KEY=... python examples/async_analysis.py <image_path>
"""

import asyncio
import sys

from ice9 import AsyncIce9
from ice9.exceptions import PartialResultError


async def analyze_single(image_path: str):
    """Analyze a single image using async/await."""
    async with AsyncIce9() as client:
        print(f"Submitting {image_path} to the free tier...")

        try:
            result = await client.analyze(image_path, tier="free")
        except PartialResultError as e:
            print(f"Warning: some services failed: {e.result.services_failed}")
            result = e.result

        print(f"Done. Image ID: {result.image_id}\n")

        for service_name in result.services_submitted:
            service = getattr(result, service_name)
            print(f"[{service_name}]")
            print(service)
            print()


async def analyze_sequential(image_paths: list[str]):
    """Analyze multiple images sequentially.

    Note: The API is optimized for real-time, single-image analysis.
    Parallelizing requests will trigger rate limits. For high-volume
    batch workloads, contact us about scaling capacity.
    """
    async with AsyncIce9() as client:
        for i, image_path in enumerate(image_paths, 1):
            print(f"[{i}/{len(image_paths)}] Analyzing {image_path}...")

            try:
                result = await client.analyze(image_path, tier="free")
                print(f"  ✓ Image ID: {result.image_id}")
            except PartialResultError as e:
                print(f"  ⚠ Partial result (some services failed)")
                result = e.result
            except Exception as e:
                print(f"  ✗ Failed: {e}")
                continue

            print()


async def analyze_with_streaming(image_path: str):
    """Analyze using SSE streaming to get results as they arrive."""
    import time

    async with AsyncIce9() as client:
        print(f"Submitting {image_path} with streaming...")
        start = time.monotonic()

        try:
            async for result in await client.analyze(image_path, tier="free", stream=True):
                elapsed = time.monotonic() - start

                if result.is_complete:
                    print(f"\n[{elapsed:.2f}s] All services complete. Image ID: {result.image_id}")
                else:
                    # Get the most recently completed service
                    latest = result.services_submitted[-1]
                    print(f"[{elapsed:.2f}s] {latest} ready")

        except PartialResultError as e:
            print(f"Warning: some services failed: {e.result.services_failed}")
            result = e.result

        print()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python examples/async_analysis.py <image_path> [image_path2 ...]")
        sys.exit(1)

    images = sys.argv[1:]

    if len(images) == 1:
        # Single image - show two patterns
        print("=== Single image analysis ===\n")
        await analyze_single(images[0])

        print("\n=== With streaming ===\n")
        await analyze_with_streaming(images[0])
    else:
        # Multiple images
        print(f"=== Analyzing {len(images)} images sequentially ===\n")
        await analyze_sequential(images)


if __name__ == "__main__":
    asyncio.run(main())
