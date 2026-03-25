import copy
import pytest

from ice9 import CENSOR_LABELS
from ice9.censor import censor
from ice9.exceptions import Ice9Error
from ice9.models import AnalysisResult

from .conftest import STATUS_COMPLETE


# ---------------------------------------------------------------------------
# Fixtures

NUDENET_PREDICTIONS = [
    {"label": "FEMALE_BREAST_EXPOSED",   "confidence": 0.85, "bbox": {"x": 100, "y": 100, "width": 80,  "height": 90}},
    {"label": "FEMALE_GENITALIA_EXPOSED","confidence": 0.72, "bbox": {"x": 150, "y": 300, "width": 60,  "height": 70}},
    {"label": "BELLY_EXPOSED",           "confidence": 0.90, "bbox": {"x": 120, "y": 200, "width": 100, "height": 80}},
    {"label": "ARMPITS_EXPOSED",         "confidence": 0.80, "bbox": {"x": 50,  "y": 80,  "width": 40,  "height": 40}},
    {"label": "FEMALE_BREAST_EXPOSED",   "confidence": 0.30, "bbox": {"x": 200, "y": 100, "width": 80,  "height": 90}},
]


@pytest.fixture
def result_with_nudenet(tmp_path):
    status = copy.deepcopy(STATUS_COMPLETE)
    status["service_results"]["nudenet"] = {
        "data": {
            "predictions": NUDENET_PREDICTIONS,
            "metadata": {"model_info": {"framework": "NudeNet+"}},
            "service": "nudenet",
            "status": "success",
        },
        "processing_time": 0.1,
        "result_created": "2026-03-09T00:00:00",
    }
    return AnalysisResult._from_status(status)


@pytest.fixture
def result_without_nudenet():
    status = copy.deepcopy(STATUS_COMPLETE)
    status["service_results"].pop("nudenet", None)
    status["services_submitted"] = ["colors"]
    return AnalysisResult._from_status(status)


@pytest.fixture
def small_image(tmp_path):
    """A 500x600 image — smaller than _API_MAX_DIMENSION, no scaling needed.
    Uses a gradient so pixelation produces a visibly different result."""
    from PIL import Image
    import numpy as np
    arr = np.zeros((600, 500, 3), dtype=np.uint8)
    arr[:, :, 0] = np.linspace(50, 200, 500, dtype=np.uint8)   # R varies across x
    arr[:, :, 1] = np.linspace(80, 150, 600, dtype=np.uint8).reshape(-1, 1)  # G varies across y
    arr[:, :, 2] = 120
    path = tmp_path / "test.jpg"
    Image.fromarray(arr).save(path)
    return path


@pytest.fixture
def large_image(tmp_path):
    """A 2048x1536 image with original-space API coordinates."""
    from PIL import Image
    path = tmp_path / "large.jpg"
    Image.new("RGB", (2048, 1536), color=(200, 180, 160)).save(path)
    return path


# ---------------------------------------------------------------------------
# CENSOR_LABELS

def test_censor_labels_includes_genitalia():
    assert "FEMALE_GENITALIA_EXPOSED" in CENSOR_LABELS
    assert "MALE_GENITALIA_EXPOSED" in CENSOR_LABELS


def test_censor_labels_includes_breasts():
    assert "FEMALE_BREAST_EXPOSED" in CENSOR_LABELS
    assert "MALE_BREAST_EXPOSED" in CENSOR_LABELS


def test_censor_labels_excludes_armpits():
    assert "ARMPITS_EXPOSED" not in CENSOR_LABELS


def test_censor_labels_excludes_belly():
    assert "BELLY_EXPOSED" not in CENSOR_LABELS


def test_censor_labels_excludes_feet():
    assert "FEET_EXPOSED" not in CENSOR_LABELS


def test_censor_labels_excludes_faces():
    assert "FACE_FEMALE" not in CENSOR_LABELS
    assert "FACE_MALE" not in CENSOR_LABELS


# ---------------------------------------------------------------------------
# censor() — basic behaviour

def test_censor_returns_pil_image(result_with_nudenet, small_image):
    from PIL import Image
    img = result_with_nudenet.censor(small_image)
    assert isinstance(img, Image.Image)


def test_censor_preserves_image_dimensions(result_with_nudenet, small_image):
    img = result_with_nudenet.censor(small_image)
    from PIL import Image
    assert img.size == Image.open(small_image).size


def test_censor_fill_draws_black_rectangle(result_with_nudenet, small_image):
    img = result_with_nudenet.censor(small_image, method="fill")
    # Breast detection at x=100, y=100, w=80, h=90 → centre (140, 145)
    r, g, b = img.getpixel((140, 145))
    assert r == 0 and g == 0 and b == 0


def test_censor_pixelate_changes_region(result_with_nudenet, small_image):
    from PIL import Image
    original = Image.open(small_image).convert("RGB")
    censored = result_with_nudenet.censor(small_image, method="pixelate")
    # Gradient image — pixelation averages blocks, changing individual pixel values
    assert censored.getpixel((140, 145)) != original.getpixel((140, 145))


def test_censor_saves_to_output_path(result_with_nudenet, small_image, tmp_path):
    output = tmp_path / "censored.jpg"
    result_with_nudenet.censor(small_image, output=output)
    assert output.exists()
    assert output.stat().st_size > 0


def test_censor_returns_image_even_when_output_given(result_with_nudenet, small_image, tmp_path):
    from PIL import Image
    output = tmp_path / "censored.jpg"
    img = result_with_nudenet.censor(small_image, output=output)
    assert isinstance(img, Image.Image)


# ---------------------------------------------------------------------------
# censor() — label and confidence filtering

def test_censor_skips_non_default_labels(result_with_nudenet, small_image):
    """BELLY_EXPOSED is not in CENSOR_LABELS — that region should be untouched."""
    from PIL import Image
    original = Image.open(small_image).convert("RGB")
    censored = result_with_nudenet.censor(small_image, method="fill")
    # Belly bbox: x=120, y=200, w=100, h=80 → centre (170, 240)
    assert censored.getpixel((170, 240)) == original.getpixel((170, 240))


def test_censor_skips_low_confidence(result_with_nudenet, small_image):
    """The breast detection at confidence=0.30 should be skipped at default threshold."""
    from PIL import Image
    original = Image.open(small_image).convert("RGB")
    censored = result_with_nudenet.censor(small_image, method="fill")
    # Low-confidence bbox: x=200, y=100, w=80, h=90 → centre (240, 145)
    assert censored.getpixel((240, 145)) == original.getpixel((240, 145))


def test_censor_custom_labels(result_with_nudenet, small_image):
    """Passing a custom label set censors only those labels."""
    from PIL import Image
    original = Image.open(small_image).convert("RGB")
    # Only censor belly (not in defaults)
    censored = result_with_nudenet.censor(small_image, method="fill", labels={"BELLY_EXPOSED"})
    # Belly centre (170, 240) should now be black
    assert censored.getpixel((170, 240)) == (0, 0, 0)
    # Breast centre (140, 145) should be untouched
    assert censored.getpixel((140, 145)) == original.getpixel((140, 145))


def test_censor_min_confidence_zero_includes_all(result_with_nudenet, small_image):
    """min_confidence=0 should apply even the 0.30-confidence detection."""
    censored = result_with_nudenet.censor(small_image, method="fill", min_confidence=0)
    # Low-confidence bbox centre (240, 145) should now be black
    assert censored.getpixel((240, 145)) == (0, 0, 0)


# ---------------------------------------------------------------------------
# censor() — coordinate scaling

def test_censor_scales_bboxes_for_large_image(result_with_nudenet, large_image):
    """Large images should use API bboxes as-is, without client-side compensation."""
    img = result_with_nudenet.censor(large_image, method="fill")
    # Breast bbox is already in original-image space: x=100, y=100, w=80, h=90.
    r, g, b = img.getpixel((140, 145))
    assert r == 0 and g == 0 and b == 0
    # Old client-side compensation would have shifted censoring to ~2x these coords.
    assert img.getpixel((280, 290)) != (0, 0, 0)


def test_censor_no_scaling_for_small_image(result_with_nudenet, small_image):
    """For a 200x200 image (below API max), bboxes are used as-is."""
    img = result_with_nudenet.censor(small_image, method="fill")
    # Breast bbox: x=100, y=100, w=80, h=90 → centre (140, 140) should be black
    assert img.getpixel((140, 140)) == (0, 0, 0)


# ---------------------------------------------------------------------------
# censor() — error cases

def test_censor_raises_without_nudenet(result_without_nudenet, small_image):
    with pytest.raises(Ice9Error, match="nudenet"):
        result_without_nudenet.censor(small_image)


def test_censor_raises_on_unknown_method(result_with_nudenet, small_image):
    with pytest.raises(ValueError, match="Unknown censor method"):
        result_with_nudenet.censor(small_image, method="blur")


def test_censor_no_detections_returns_unchanged_image(tmp_path, small_image):
    """A result with no nudenet predictions should return the image unmodified."""
    from PIL import Image
    status = copy.deepcopy(STATUS_COMPLETE)
    status["service_results"]["nudenet"] = {
        "data": {"predictions": [], "service": "nudenet", "status": "success"},
        "processing_time": 0.1,
        "result_created": "2026-03-09T00:00:00",
    }
    result = AnalysisResult._from_status(status)
    original = Image.open(small_image).convert("RGB")
    censored = result.censor(small_image)
    assert list(censored.getdata()) == list(original.getdata())
