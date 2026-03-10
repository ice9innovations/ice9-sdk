"""
Submit an image to the free tier and print the results.

The free tier runs a fixed set of fast services on your image:
  - nudenet:          content moderation (detects explicit content)
  - content_analysis: scene type, anatomy, gender breakdown, intimacy level
  - colors:           dominant colors in the image
  - metadata:         file format, dimensions, EXIF data
  - ocr:              any text found in the image
  - qr:               any QR codes or barcodes found in the image

Results are usually ready in a few seconds.

Usage:
    ICE9_API_KEY=... python examples/free_tier.py <image_path>
"""

import sys

from ice9 import Ice9
from ice9.exceptions import PartialResultError


def main(image_path):
    client = Ice9()  # reads ICE9_API_KEY from environment

    print(f"Submitting {image_path} to the free tier...")
    try:
        result = client.analyze(image_path, tier="free")
    except PartialResultError as e:
        # Some services failed but we still have partial results
        print(f"Warning: some services failed: {e.result.services_failed}")
        result = e.result

    print(f"Done. Image ID: {result.image_id}\n")

    for service_name in result.services_submitted:
        service = getattr(result, service_name)
        print(f"[{service_name}]")
        print(service)
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python examples/free_tier.py <image_path>")
        sys.exit(1)
    main(sys.argv[1])
