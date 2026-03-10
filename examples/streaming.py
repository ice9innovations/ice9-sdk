"""
Submit an image and print results as each service finishes.

Normally client.analyze() waits for everything to complete before returning.
With stream=True it returns results one service at a time, as they arrive.
This is useful when you only need one service (like nudenet) and don't want
to wait for the slower ones to finish.

Usage:
    ICE9_API_KEY=... python examples/streaming.py <image_path>
"""

import sys
import time

from ice9 import Ice9
from ice9.exceptions import PartialResultError


def main(image_path):
    client = Ice9()  # reads ICE9_API_KEY from environment

    print(f"Submitting {image_path}...")
    start = time.monotonic()

    try:
        for result in client.analyze(image_path, tier="free", stream=True):
            elapsed = time.monotonic() - start

            if result.is_complete:
                print(f"\n[{elapsed:.2f}s] All services done. Image ID: {result.image_id}")
            else:
                # Figure out which service just arrived by seeing what's new
                latest = result.services_submitted[-1]
                print(f"[{elapsed:.2f}s] {latest} ready")

    except PartialResultError as e:
        print(f"Warning: some services failed: {e.result.services_failed}")
        result = e.result

    print()
    print("Results:")
    for service_name in result.services_submitted:
        service = getattr(result, service_name)
        print(f"[{service_name}]")
        print(service)
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python examples/streaming.py <image_path>")
        sys.exit(1)
    main(sys.argv[1])
