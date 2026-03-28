"""
Submit an image to the premium tier and print the results.

The premium tier runs everything in the basic tier plus three cloud models:
  - gemini   (Google)
  - gpt_nano (OpenAI)
  - haiku    (Anthropic)

More models means more votes in the noun consensus, which means higher
confidence in the validated nouns. The cloud models also tend to produce
richer, more accurate descriptions than the local models.

Runs more services than basic tier (15 vs 10). Current benchmarks show
13-16 seconds but expect this to increase with more usage and load.

Usage:
    ICE9_API_KEY=... python examples/premium_tier.py <image_path>
"""

import sys

from ice9 import Ice9, CENSOR_LABELS
from ice9.exceptions import AnalysisTimeoutError, PartialResultError

TIMEOUT = 60.0  # premium runs more services than basic, allow extra time

# The cloud models that premium adds on top of basic
CLOUD_MODELS = ("gemini", "gpt_nano", "haiku")

# Local VLMs (present in basic and premium)
LOCAL_MODELS = ("blip", "florence2", "moondream", "ollama", "qwen")

# Services shown in their own dedicated sections below
ALREADY_SHOWN = ("nudenet", "colors", "metadata", "ocr", "qr",
                 "florence2_grounding", "yolo_v8", "noun_consensus",
                 "caption_summary", "verb_consensus", "consensus")


def main(image_path):
    client = Ice9(timeout=TIMEOUT)

    print(f"Submitting {image_path} to the premium tier...")
    try:
        result = client.analyze(image_path, tier="premium")
    except AnalysisTimeoutError:
        print(f"Timed out after {TIMEOUT}s. The server may be under load — try again.")
        sys.exit(1)
    except PartialResultError as e:
        print(f"Warning: some services failed: {e.result.services_failed}")
        result = e.result

    print(f"Done. Image ID: {result.image_id}\n")

    # -----------------------------------------------------------------------
    # Summary caption

    if result.caption:
        print(f"Summary: {result.caption}")
        print()

    # -----------------------------------------------------------------------
    # Validated nouns
    # With more models voting, confidence here is higher than basic tier.

    if result.nouns is not None:
        print("Validated nouns:")
        for noun in result.nouns.validated:
            confirmed = "(confirmed)" if noun["grounding_validated"] else ""
            print(f"  {noun['canonical']:20s}  votes={noun['vote_count']}  {confirmed}")
        print()

    # -----------------------------------------------------------------------
    # Cloud model outputs — the premium differentiator

    print("Cloud model outputs:")
    for service_name in CLOUD_MODELS:
        service = getattr(result, service_name)
        if service is not None and service.text:
            print(f"  {service_name}: {service.text}")
    print()

    # -----------------------------------------------------------------------
    # Local model outputs

    print("Local model outputs:")
    for service_name in LOCAL_MODELS:
        service = getattr(result, service_name)
        if service is not None and service.text:
            print(f"  {service_name}: {service.text}")
    print()

    # -----------------------------------------------------------------------
    # Object detection — yolo_v8

    if result.yolo_v8 is not None:
        if result.yolo_v8.predictions:
            print(f"Objects detected by YOLO ({len(result.yolo_v8.predictions)} total):")
            for obj in result.yolo_v8.predictions:
                print(f"  {obj['label']:25s}  confidence={obj['confidence']:.0%}  bbox={obj['bbox']}")
        else:
            print("YOLO — no objects detected")
        print()

    # -----------------------------------------------------------------------
    # Florence-2 bounding boxes

    if result.nouns is not None:
        if result.nouns.regions:
            print(f"Florence-2 grounded regions ({len(result.nouns.regions)} total):")
            for region in result.nouns.regions:
                label = region.get("label") or region.get("text") or "unknown"
                bbox = region.get("bbox") or region.get("quad_box")
                print(f"  {label:25s}  {bbox}")
        print()

    # -----------------------------------------------------------------------
    # Content moderation

    flagged = result.nsfw_detections(labels=CENSOR_LABELS)
    if flagged:
        print(f"Content moderation — {len(flagged)} flagged detection(s):")
        for detection in flagged:
            print(f"  {detection['label']}  confidence={detection['confidence']:.0%}")
    else:
        print("Content moderation — no flagged detections")
    print()

    # -----------------------------------------------------------------------
    # Full result as JSON

    print("--- Full result as JSON ---")
    print(result.to_json(indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python examples/premium_tier.py <image_path>")
        sys.exit(1)
    main(sys.argv[1])
