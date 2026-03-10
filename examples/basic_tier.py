"""
Submit an image to the basic tier and print the results.

The basic tier runs several AI models on your image and combines their
outputs into a summary. It takes longer than the free tier — up to 2 minutes
— because it waits for all the models to finish before producing a result.

What you get back:
  - A summary caption describing the image
  - A list of nouns the models agreed on (e.g. "dog", "person", "car")
  - Bounding boxes showing where those nouns are in the image
  - A content moderation check
  - What each individual model said

Usage:
    ICE9_API_KEY=... python examples/basic_tier.py <image_path>
"""

import sys

from ice9 import Ice9
from ice9.exceptions import AnalysisTimeoutError, PartialResultError

TIMEOUT = 120.0  # seconds — the pipeline can take a while


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

    if result.caption_summary is not None:
        print(f"Summary: {result.caption_summary.summary_caption}")
        print()

    # -----------------------------------------------------------------------
    # Validated nouns
    # These are the things the models agreed are in the image. The ones marked
    # as grounding_validated were also confirmed by Florence-2, which found
    # matching regions in the image — so we're extra confident about those.

    if result.noun_consensus is not None:
        print("Nouns found in this image:")
        for noun in result.noun_consensus.nouns:
            if noun["grounding_validated"]:
                note = "(confirmed)"
            else:
                note = ""
            print(f"  {noun['canonical']}  votes={noun['vote_count']}  {note}")
        print()

    # -----------------------------------------------------------------------
    # Bounding boxes
    # Florence-2 found these regions in the image, one per noun phrase.

    if result.florence2_grounding is not None:
        if result.florence2_grounding.predictions:
            print(f"Regions found by Florence-2 ({len(result.florence2_grounding.predictions)} total):")
            for region in result.florence2_grounding.predictions:
                label = region.get("label") or region.get("text") or "unknown"
                bbox = region.get("bbox") or region.get("quad_box")
                print(f"  {label}  {bbox}")
            print()

    # -----------------------------------------------------------------------
    # Content moderation
    # nudenet checks for explicit content. Detections below 50% confidence
    # are ignored.

    if result.nudenet is not None:
        flagged = []
        for detection in result.nudenet.predictions:
            if detection["confidence"] >= 0.5:
                flagged.append(detection)

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
