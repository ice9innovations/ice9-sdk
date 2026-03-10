"""
Retrieve results from a previously analyzed image.

This demonstrates how to fetch analysis results using an image_id from a
previous analysis. This is useful for:
- Retrieving results across different sessions
- Building dashboards from historical data
- Avoiding re-analysis of the same image

Usage:
    ICE9_API_KEY=... python examples/retrieve_result.py <image_id>

Example workflow:
    # First, analyze an image
    result = client.analyze("photo.jpg")
    print(f"Image ID: {result.image_id}")  # Save this ID

    # Later, retrieve the same results
    result = client.get_result(12345)
    print(result.nudenet)
"""

import sys

from ice9 import Ice9
from ice9.exceptions import Ice9Error


def main(image_id):
    client = Ice9()  # reads ICE9_API_KEY from environment

    print(f"Fetching results for image {image_id}...")

    try:
        result = client.get_result(int(image_id))
    except Ice9Error as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"Success! Retrieved analysis for image {result.image_id}\n")
    print(f"Services: {', '.join(result.services_submitted)}")
    print(f"Image filename: {result._raw.get('image_filename', 'N/A')}")
    print(f"Image group: {result._raw.get('image_group', 'N/A')}")
    print(f"Analyzed at: {result._raw.get('image_created', 'N/A')}")

    if result.services_failed:
        print(f"\nFailed services: {result.services_failed}")

    print("\nService results:")
    for service_name in result.services_submitted:
        service = getattr(result, service_name)
        if service:
            print(f"  [{service_name}] ✓")
        else:
            print(f"  [{service_name}] ✗")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python examples/retrieve_result.py <image_id>")
        print("\nExample:")
        print("  python examples/retrieve_result.py 12345")
        sys.exit(1)
    main(sys.argv[1])
