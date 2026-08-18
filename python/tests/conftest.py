import base64
import io
import pytest


# A minimal 1x1 white PNG. Used wherever a real image file is needed without
# requiring PIL or a fixture image on disk.
_MINIMAL_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
    "z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="
)
MINIMAL_PNG = base64.b64decode(_MINIMAL_PNG_B64)


@pytest.fixture
def png_file(tmp_path):
    """A temporary 1x1 PNG file. Returns the path."""
    path = tmp_path / "test.png"
    path.write_bytes(MINIMAL_PNG)
    return path


@pytest.fixture
def png_bytes_io():
    """A 1x1 PNG as an in-memory file object."""
    buf = io.BytesIO(MINIMAL_PNG)
    buf.name = "test.png"
    return buf


# ---------------------------------------------------------------------------
# Canned API responses used across multiple test modules.

ANALYZE_RESPONSE = {
    "image_id": 42,
    "trace_id": "test-trace-001",
    "tier": "basic",
    "services_submitted": ["nudenet", "colors", "metadata", "ocr", "qr"],
    "image_width": 1,
    "image_height": 1,
}

STATUS_COMPLETE = {
    "image_id": 42,
    "image_filename": "test.png",
    "image_group": "api",
    "image_created": "2026-03-08T12:00:00",
    "services_submitted": ["nudenet", "colors", "metadata", "ocr", "qr"],
    "services_completed": {
        "nudenet":  {"status": "success", "result_created": "2026-03-08T12:00:01", "processing_time": 0.4},
        "colors":   {"status": "success", "result_created": "2026-03-08T12:00:01", "processing_time": 0.1},
        "metadata": {"status": "success", "result_created": "2026-03-08T12:00:01", "processing_time": 0.1},
        "ocr":      {"status": "success", "result_created": "2026-03-08T12:00:01", "processing_time": 0.2},
        "qr":       {"status": "success", "result_created": "2026-03-08T12:00:01", "processing_time": 0.1},
    },
    "services_pending": [],
    "services_failed": {},
    "progress": "5/5",
    "is_complete": True,
    "primary_complete": True,
    "downstream_pending": [],
    "service_results": {
        "nudenet":  {"data": {"detections": []},            "processing_time": 0.4, "result_created": "2026-03-08T12:00:01"},
        "colors":   {"data": {"dominant": ["#ffffff"]},     "processing_time": 0.1, "result_created": "2026-03-08T12:00:01"},
        "metadata": {"data": {"width": 1, "height": 1},    "processing_time": 0.1, "result_created": "2026-03-08T12:00:01"},
        "ocr":      {"data": {"text": ""},                  "processing_time": 0.2, "result_created": "2026-03-08T12:00:01"},
        "qr":       {"data": {"codes": []},                 "processing_time": 0.1, "result_created": "2026-03-08T12:00:01"},
        # Injected without "data" wrapper — canonical schema (all data in full_analysis)
        "content_analysis": {
            "full_analysis": {
                "category": "safe",
                "scene": {
                    "people": 0,
                    "gender": {
                        "presentation": "unknown",
                        "mixed": False,
                        "confidence": 0.0,
                    },
                },
                "activity_analysis": {
                    "scene_type": "safe",
                    "intimacy_level": "none",
                    "people_count": 0,
                    "activities_detected": [],
                    "spatial_relationships": [],
                },
                "anatomy_exposed": [],
                "gender_breakdown": {},
                "person_attributions": [],
                "semantic_validation": {},
            },
            "created": "2026-03-08T12:00:01",
            "analysis_version": "1.0",
        },
    },
    "merged_boxes": [],
    "consensus": None,
    "postprocessing": [],
    "noun_consensus": None,
    "verb_consensus": None,
    "sam3": None,
    "caption_summary": None,
    "rembg": {
        "model": "birefnet-general",
        "png_b64": "aGVsbG8=",
        "premasked": False,
        "processing_time": 1.2,
        "shape": [512, 512],
        "updated_at": "2026-03-08T12:00:02",
    },
    "service_dispatch": [],
    "consensus_complete": False,
    "content_analysis_complete": False,
    "noun_consensus_complete": False,
    "verb_consensus_complete": False,
    "sam3_complete": False,
    "caption_summary_complete": False,
    "rembg_complete": False,
}

# Basic-tier status that includes noun_consensus and caption_summary injected
# directly into service_results (no "data" wrapper — they come from separate
# tables and are injected by the API without the standard results-table envelope).
STATUS_COMPLETE_BASIC = {
    **STATUS_COMPLETE,
    "services_submitted": ["nudenet", "colors", "moondream", "qwen",
                           "florence2_grounding", "noun_consensus", "caption_summary"],
    "service_results": {
        **STATUS_COMPLETE["service_results"],
        "moondream": {
            "data": {"predictions": [{"text": "a dog sitting on a wooden floor"}]},
            "processing_time": 1.2, "result_created": "2026-03-08T12:00:02",
        },
        "qwen": {
            "data": {"predictions": [{"text": "a brown dog on a hardwood floor"}]},
            "processing_time": 2.1, "result_created": "2026-03-08T12:00:03",
        },
        "florence2_grounding": {
            "data": {"predictions": [
                {"label": "dog", "bbox": {"x": 50, "y": 80, "width": 200, "height": 180}},
            ]},
            "processing_time": 0.9, "result_created": "2026-03-08T12:00:04",
        },
        # Injected without "data" wrapper — the new post-fix format
        "noun_consensus": {
            "nouns": [
                {"canonical": "dog", "category": "animal", "confidence": 1.0,
                 "grounding_validated": True, "vote_count": 2,
                 "services": ["moondream", "qwen"], "surface_forms": ["dog"]},
            ],
            "nouns_all": [
                {"canonical": "dog", "category": "animal", "confidence": 1.0,
                 "grounding_validated": True, "vote_count": 2,
                 "services": ["moondream", "qwen"], "surface_forms": ["dog"]},
                {"canonical": "floor", "category": "object", "confidence": 0.4,
                 "grounding_validated": False, "vote_count": 1,
                 "services": ["moondream"], "surface_forms": ["floor"]},
            ],
            "category_tally": [{"category": "animal", "count": 1}],
            "services_present": ["moondream", "qwen"],
            "service_count": 2,
            "created_at": "2026-03-08T12:00:05",
            "updated_at": "2026-03-08T12:00:05",
        },
        "caption_summary": {
            "summary_caption": "A dog is sitting on a hardwood floor.",
            "model": "qwen",
            "services_present": ["moondream", "qwen"],
            "service_count": 2,
            "created_at": "2026-03-08T12:00:06",
            "updated_at": "2026-03-08T12:00:06",
        },
    },
    "postprocessing": [],
}

STATUS_COMPLETE_WITH_TERMINAL_FAILURE = {
    **STATUS_COMPLETE,
    "services_failed": {"pose": "worker returned terminal failure"},
    "service_results": {
        **STATUS_COMPLETE["service_results"],
        "pose": {
            "status": "failed",
            "error_message": "worker returned terminal failure",
            "data": None,
            "processing_time": 0.3,
            "result_created": "2026-03-08T12:00:02",
        },
    },
    "services_submitted": [*STATUS_COMPLETE["services_submitted"], "pose"],
}

TIERS_RESPONSE = {
    "tiers": {
        "basic": ["colors", "content_analysis", "metadata", "nsfw2", "nudenet", "yolo_v8"],
        "cloud": [
            "caption_summary", "colors", "content_analysis", "face", "florence2_grounding",
            "gemini", "gpt_nano", "haiku", "metadata", "noun_consensus", "nsfw2",
            "nudenet", "ocr", "pose", "postprocessing_orchestrator", "qr", "rembg",
            "xai", "yolo_v8",
        ],
        "extra": [
            "blip", "caption_summary", "colors", "content_analysis", "face", "florence2",
            "florence2_grounding", "gemini", "gpt_nano", "haiku", "joycaption",
            "metadata", "moondream", "noun_consensus", "nsfw2", "nudenet", "ocr",
            "ollama", "pose", "postprocessing_orchestrator", "qr", "qwen", "rembg",
            "xai", "yolo_v8",
        ],
        "premium": [
            "blip", "caption_summary", "colors", "content_analysis", "face", "florence2",
            "florence2_grounding", "joycaption", "metadata", "moondream",
            "noun_consensus", "nsfw2", "nudenet", "ocr", "ollama", "pose",
            "postprocessing_orchestrator", "qr", "qwen", "rembg", "yolo_v8",
        ],
    }
}

SERVICES_RESPONSE = {
    "services": [
        "blip", "caption_summary", "colors", "content_analysis", "face", "florence2",
        "florence2_grounding", "gemini", "gpt_nano", "haiku", "joycaption",
        "metadata", "moondream", "noun_consensus", "nsfw2", "nudenet", "ocr",
        "ollama", "pose", "postprocessing_orchestrator", "qr", "qwen", "rembg",
        "xai", "yolo_v8",
    ]
}
