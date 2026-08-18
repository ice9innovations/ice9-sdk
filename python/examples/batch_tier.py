"""
Parallel processing with the extra tier.

The extra tier includes the broadest current model set and is useful for
high-volume workloads where you need richer analysis across diverse image
types.

Key differences from basic/premium tiers:
- Optimized for batch processing (parallelization supported)
- Uses multiple VLM and consensus services
- Includes the baseline NSFW/content-analysis services
- Higher latency per image, but designed for throughput

For lower-latency analysis of individual images, use basic or premium tier.

Usage:
    ICE9_API_KEY=... python examples/batch_tier.py image1.jpg image2.jpg ...
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from ice9 import Ice9
from ice9.exceptions import Ice9Error, PartialResultError


def analyze_image(client: Ice9, image_path: str) -> dict:
    """Analyze a single image on the extra tier."""
    try:
        result = client.analyze(image_path, tier="extra")
        return {
            "path": image_path,
            "success": True,
            "image_id": result.image_id,
            "services": len(result.services_submitted),
            "failed": list(result.services_failed.keys()) if result.services_failed else [],
        }
    except PartialResultError as e:
        return {
            "path": image_path,
            "success": True,
            "image_id": e.result.image_id,
            "services": len(e.result.services_submitted),
            "failed": list(e.result.services_failed.keys()),
            "partial": True,
        }
    except Ice9Error as e:
        return {
            "path": image_path,
            "success": False,
            "error": str(e),
        }


def main(image_paths: list[str], max_workers: int = 10):
    """
    Process images in parallel using the extra tier.

    Args:
        image_paths: List of image file paths to process
        max_workers: Maximum number of concurrent requests (default: 10)
    """
    client = Ice9()  # reads ICE9_API_KEY from environment

    print(f"Processing {len(image_paths)} images with extra tier...")
    print(f"Max concurrent workers: {max_workers}\n")

    start_time = time.time()
    results = []

    # Independent analyses can be parallelized within your account's rate limits.
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_path = {
            executor.submit(analyze_image, client, path): path
            for path in image_paths
        }

        # Process results as they complete
        for i, future in enumerate(as_completed(future_to_path), 1):
            result = future.result()
            results.append(result)

            # Progress indicator
            if result["success"]:
                status = "⚠" if result.get("partial") else "✓"
                print(f"[{i}/{len(image_paths)}] {status} {result['path']}")
                if result.get("failed"):
                    print(f"           Failed services: {', '.join(result['failed'])}")
            else:
                print(f"[{i}/{len(image_paths)}] ✗ {result['path']}")
                print(f"           Error: {result['error']}")

    elapsed = time.time() - start_time

    # Summary
    print(f"\n{'='*60}")
    print("Summary:")
    print(f"  Total images: {len(results)}")
    print(f"  Successful:   {sum(1 for r in results if r['success'])}")
    print(f"  Failed:       {sum(1 for r in results if not r['success'])}")
    print(f"  Partial:      {sum(1 for r in results if r.get('partial'))}")
    print(f"  Total time:   {elapsed:.1f}s")
    print(f"  Avg per image: {elapsed/len(results):.1f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python examples/batch_tier.py <image1> <image2> ...")
        print("\nExample:")
        print("  python examples/batch_tier.py images/*.jpg")
        sys.exit(1)

    images = sys.argv[1:]

    # You can adjust max_workers based on your rate limits
    # Parallel workloads still have rate limits
    main(images, max_workers=10)
