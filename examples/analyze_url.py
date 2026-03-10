"""
Analyze an image from a URL.

The SDK automatically detects URLs and downloads the image before submitting
it to the API. This preserves ice9's design principle: the API doesn't store
images, and analysis is performed on-the-fly.

Features:
- Automatic URL detection (http:// or https://)
- Streaming download (handles large images up to 10MB)
- Content-type validation
- Works with both sync and async clients

Usage:
    ICE9_API_KEY=... python examples/analyze_url.py <image_url>

Example:
    ICE9_API_KEY=... python examples/analyze_url.py https://example.com/photo.jpg
"""

import sys

from ice9 import Ice9
from ice9.exceptions import Ice9Error, PartialResultError


def main(image_url: str):
    client = Ice9()  # reads ICE9_API_KEY from environment

    print(f"Analyzing image from URL...")
    print(f"URL: {image_url}\n")

    try:
        result = client.analyze(image_url, tier="free")
    except PartialResultError as e:
        print(f"Warning: some services failed: {e.result.services_failed}")
        result = e.result
    except Ice9Error as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"✓ Analysis complete. Image ID: {result.image_id}\n")

    # Display results
    for service_name in result.services_submitted:
        service = getattr(result, service_name)
        print(f"[{service_name}]")

        # Show a preview of the data
        if service:
            if hasattr(service, "text") and service.text:
                print(f"  {service.text}")
            elif hasattr(service, "predictions") and service.predictions:
                print(f"  {len(service.predictions)} predictions")
            else:
                print(f"  ✓")
        else:
            print(f"  (not available)")

        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python examples/analyze_url.py <image_url>")
        print("\nExample:")
        print("  python examples/analyze_url.py https://example.com/photo.jpg")
        sys.exit(1)

    url = sys.argv[1]

    # Validate it looks like a URL
    if not url.startswith(("http://", "https://")):
        print(f"Error: '{url}' doesn't look like a URL")
        print("URLs must start with http:// or https://")
        sys.exit(1)

    main(url)
