"""
Submit an image to the basic tier and print the results.

The basic tier runs several AI models on your image and combines their
outputs into a summary. It typically completes in 8-10 seconds (P50: 7.6s,
P95: 34s) and waits for all the models to finish before producing a result.

What you get back:
  - A summary caption describing the image
  - A list of nouns the models agreed on (e.g. "dog", "person", "car")
  - Bounding boxes showing where those nouns are in the image
  - The baseline NSFW screening signals
  - What each individual model said

Usage:
    ICE9_API_KEY=... python examples/basic_tier.py <image_path>
"""

import sys

from ice9 import Ice9
from ice9.exceptions import AnalysisTimeoutError, PartialResultError

TIMEOUT = 45.0  # basic tier typically completes in 8-10s, 45s allows for slow images


def main(image_path):
    client = Ice9(timeout=TIMEOUT)

    print(f"Submitting {image_path} to the basic tier...")
    try:
        result = client.analyze(image_path, tier="basic")
    except AnalysisTimeoutError:
        print(f"Timed out after {TIMEOUT}s. The server may be under load — try again.")
        sys.exit(1)
    except PartialResultError as e:
        # Some services failed but we still have partial results
        print(f"Warning: some services failed: {e.result.services_failed}")
        result = e.result

    print(f"Done. Image ID: {result.image_id}\n")

    # -----------------------------------------------------------------------
    # Summary caption
    # A single description of the image, synthesised from all the AI models.

    if result.caption:
        print(f"Summary: {result.caption}")
        print()

    # -----------------------------------------------------------------------
    # Validated nouns
    # These are the things the models agreed are in the image. The ones marked
    # as grounding_validated were also confirmed by Florence-2, which found
    # matching regions in the image — so we're extra confident about those.

    if result.nouns is not None:
        print("Nouns found in this image:")
        for noun in result.nouns.validated:
            if noun["grounding_validated"]:
                note = "(confirmed)"
            else:
                note = ""
            print(f"  {noun['canonical']}  votes={noun['vote_count']}  {note}")
        print()

    # -----------------------------------------------------------------------
    # Bounding boxes
    # Florence-2 found these regions in the image, one per noun phrase.

    if result.nouns is not None:
        if result.nouns.regions:
            print(f"Regions found by Florence-2 ({len(result.nouns.regions)} total):")
            for region in result.nouns.regions:
                label = region.get("label") or region.get("text") or "unknown"
                bbox = region.get("bbox") or region.get("quad_box")
                print(f"  {label}  {bbox}")
            print()

    # -----------------------------------------------------------------------
    # Free-tier moderation baseline
    # Every tier includes nudenet, so this helper works consistently across
    # basic, cloud, extra, and premium.

    flagged = result.nsfw_detections()
    if flagged:
        print(f"Content moderation — {len(flagged)} flagged detection(s):")
        for detection in flagged:
            print(f"  {detection['label']}  confidence={detection['confidence']:.0%}")
    else:
        print("Content moderation — no flagged detections")
    print()

    # -----------------------------------------------------------------------
    # Individual model outputs
    # What each AI model said about the image before the results were combined.

    # These are the services we already showed above — skip them here
    already_shown = ("nudenet", "colors", "metadata", "ocr", "qr",
                     "florence2_grounding", "noun_consensus",
                     "caption_summary", "verb_consensus", "consensus")

    print("Individual model outputs:")
    for service_name in result.services_submitted:
        if service_name in already_shown:
            continue
        service = getattr(result, service_name)
        if service is not None and service.text:
            print(f"  {service_name}: {service.text}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python examples/basic_tier.py <image_path>")
        sys.exit(1)
    main(sys.argv[1])
