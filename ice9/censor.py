from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import AnalysisResult

# Labels that warrant censoring by default. Deliberately excludes belly,
# armpits, feet, and faces — NudeNet detects all of these, but they are not
# content that most applications need to redact.
CENSOR_LABELS: frozenset[str] = frozenset({
    "FEMALE_BREAST_EXPOSED",
    "MALE_BREAST_EXPOSED",
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "BUTTOCKS_EXPOSED",
    "ANUS_EXPOSED",
})

# The API normalizes uploads to this maximum dimension before running workers.
# Bounding box coordinates are in that normalized space.
_API_MAX_DIMENSION = 1024


def censor(
    result: AnalysisResult,
    image: str | Path,
    *,
    method: str = "fill",
    labels: frozenset[str] | set[str] | None = None,
    min_confidence: float = 0.5,
    output: str | Path | None = None,
):
    """Draw censoring over nudenet detections on the original image.

    Args:
        result:         An AnalysisResult that includes nudenet output.
        image:          Path to the original image file.
        method:         One of 'fill' (black rectangle) or 'pixelate'.
        labels:         Set of nudenet labels to censor. Defaults to CENSOR_LABELS,
                        which covers genitalia, breasts, and buttocks. Pass a custom
                        set to expand or restrict what gets redacted.
        min_confidence: Minimum detection confidence to act on. Default 0.5.
        output:         If given, save the censored image to this path.

    Returns:
        A PIL Image with censored regions applied.

    Raises:
        Ice9Error:   nudenet results are not present on the result.
        ValueError:  Unknown method.
        ImportError: Pillow is not installed.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        raise ImportError(
            "Pillow is required for image censoring: pip install Pillow"
        ) from None

    from .exceptions import Ice9Error

    if result.nudenet is None:
        raise Ice9Error(
            "nudenet results are not present — was nudenet included in the tier?"
        )

    if method not in ("fill", "pixelate"):
        raise ValueError(f"Unknown censor method {method!r}. Choose 'fill' or 'pixelate'.")

    effective_labels = labels if labels is not None else CENSOR_LABELS
    predictions = result.nudenet._data.get("predictions") or []

    img = Image.open(image).convert("RGB")
    orig_w, orig_h = img.size

    # The API resizes to _API_MAX_DIMENSION on the longest side before processing.
    # Scale bbox coordinates back to original image space.
    longest = max(orig_w, orig_h)
    if longest > _API_MAX_DIMENSION:
        bbox_scale = longest / _API_MAX_DIMENSION
    else:
        bbox_scale = 1.0

    for pred in predictions:
        if pred.get("label") not in effective_labels:
            continue
        if pred.get("confidence", 0) < min_confidence:
            continue

        raw = pred["bbox"]
        x1 = int(raw["x"] * bbox_scale)
        y1 = int(raw["y"] * bbox_scale)
        x2 = int((raw["x"] + raw["width"]) * bbox_scale)
        y2 = int((raw["y"] + raw["height"]) * bbox_scale)

        # Clamp to image bounds
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(orig_w, x2), min(orig_h, y2)

        if x2 <= x1 or y2 <= y1:
            continue

        if method == "fill":
            draw = ImageDraw.Draw(img)
            draw.rectangle([x1, y1, x2, y2], fill=(0, 0, 0))

        elif method == "pixelate":
            region = img.crop((x1, y1, x2, y2))
            block = max(8, min(x2 - x1, y2 - y1) // 8)
            small = region.resize(
                (max(1, (x2 - x1) // block), max(1, (y2 - y1) // block)),
                Image.NEAREST,
            )
            pixelated = small.resize((x2 - x1, y2 - y1), Image.NEAREST)
            img.paste(pixelated, (x1, y1))

    if output is not None:
        img.save(output)

    return img
