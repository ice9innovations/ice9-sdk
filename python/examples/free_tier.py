"""
Submit an image to the baseline tier and print the results.

The basic tier is the moderation baseline for the whole product:
  - nudenet:          raw NSFW detections with boxes and confidence scores
  - content_analysis: higher-level scene and anatomy summary derived from nudenet

It may also include utility signals like colors, metadata, OCR, and QR parsing,
but the main purpose of this example is fast NSFW screening.

Results are usually ready in under a second (P50: 0.5s, P90: 5.6s).

Usage:
    ICE9_API_KEY=... python examples/free_tier.py <image_path>
"""

import sys

from ice9 import Ice9
from ice9.exceptions import PartialResultError


def main(image_path):
    client = Ice9()  # reads ICE9_API_KEY from environment

    print(f"Submitting {image_path} to the baseline tier...")
    try:
        result = client.analyze(image_path)
    except PartialResultError as e:
        # Some services failed but we still have partial results
        print(f"Warning: some services failed: {e.result.services_failed}")
        result = e.result

    if result.is_nsfw is True:
        print("NSFW: yes")
        print(f"Reason: {result.moderation.reason}")
        if result.scene:
            print(f"Scene: {result.scene.type} / {result.scene.intimacy}")
        result.moderation.censor(image_path, output="censored.jpg")
        print("Censored copy saved to censored.jpg")
    elif result.is_nsfw is False:
        print("NSFW: no")
        print(f"Reason: {result.moderation.reason}")
        if result.scene:
            print(f"Scene: {result.scene.type} / {result.scene.intimacy}")
    else:
        print("NSFW: unknown")
        print(f"Reason: {result.moderation.reason}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python examples/free_tier.py <image_path>")
        sys.exit(1)
    main(sys.argv[1])
