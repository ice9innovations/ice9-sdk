import json
from pathlib import Path

import pytest

from ice9.models import AnalysisResult, ServiceResult

from .conftest import (
    STATUS_COMPLETE,
    STATUS_COMPLETE_BASIC,
    STATUS_COMPLETE_WITH_TERMINAL_FAILURE,
)


def _load_fixture(name: str) -> dict:
    path = Path(__file__).parent / "fixtures" / name
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# ServiceResult

def test_service_result_attribute_access():
    sr = ServiceResult({"detections": [], "safe": True})
    assert sr.detections == []
    assert sr.safe is True


def test_service_result_missing_key_raises_attribute_error():
    sr = ServiceResult({"detections": []})
    with pytest.raises(AttributeError, match="no attribute 'missing'"):
        _ = sr.missing


def test_service_result_attribute_error_lists_available_keys():
    sr = ServiceResult({"detections": [], "safe": True})
    with pytest.raises(AttributeError) as exc_info:
        _ = sr.missing
    assert "detections" in str(exc_info.value)
    assert "safe" in str(exc_info.value)


def test_service_result_processing_time():
    sr = ServiceResult({"x": 1}, processing_time=0.42)
    assert sr.processing_time == 0.42


def test_service_result_none_data_is_empty():
    sr = ServiceResult(None)
    assert not sr


def test_service_result_bool_false_when_empty():
    sr = ServiceResult({})
    assert not sr


def test_service_result_bool_true_when_populated():
    sr = ServiceResult({"key": "value"})
    assert sr


def test_service_result_predictions_returns_list():
    sr = ServiceResult({"predictions": [{"label": "DOG", "confidence": 0.9}]})
    assert sr.predictions == [{"label": "DOG", "confidence": 0.9}]


def test_service_result_predictions_returns_empty_list_when_absent():
    sr = ServiceResult({"dominant": ["#ffffff"]})
    assert sr.predictions == []


def test_service_result_predictions_returns_empty_list_when_none():
    sr = ServiceResult({"predictions": None})
    assert sr.predictions == []


def test_service_result_flagged_predictions_uses_default_moderation_labels():
    sr = ServiceResult({
        "predictions": [
            {"label": "FEMALE_BREAST_EXPOSED", "confidence": 0.9},
            {"label": "BELLY_EXPOSED", "confidence": 0.99},
            {"label": "FEMALE_GENITALIA_EXPOSED", "confidence": 0.4},
        ]
    })
    assert sr.flagged_predictions() == [
        {"label": "FEMALE_BREAST_EXPOSED", "confidence": 0.9},
    ]


def test_service_result_flagged_predictions_accepts_custom_labels():
    sr = ServiceResult({
        "predictions": [
            {"label": "BELLY_EXPOSED", "confidence": 0.99},
            {"label": "ARMPITS_EXPOSED", "confidence": 0.8},
        ]
    })
    assert sr.flagged_predictions(labels={"BELLY_EXPOSED"}) == [
        {"label": "BELLY_EXPOSED", "confidence": 0.99},
    ]


def test_service_result_text_returns_predictions_text():
    sr = ServiceResult({"predictions": [{"text": "a dog on a floor"}]})
    assert sr.text == "a dog on a floor"


def test_service_result_text_returns_none_when_no_predictions():
    sr = ServiceResult({"detections": [], "safe": True})
    assert sr.text is None


def test_service_result_text_returns_none_when_predictions_empty():
    sr = ServiceResult({"predictions": []})
    assert sr.text is None


def test_service_result_text_returns_none_when_prediction_has_no_text():
    sr = ServiceResult({"predictions": [{"label": "something", "confidence": 0.9}]})
    assert sr.text is None


def test_service_result_repr_shows_keys():
    sr = ServiceResult({"detections": [], "safe": True})
    r = repr(sr)
    assert "detections" in r
    assert "safe" in r


# ---------------------------------------------------------------------------
# AnalysisResult — construction

def test_from_status_populates_image_id():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    assert result.image_id == 42


def test_from_status_populates_services_submitted():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    assert "nudenet" in result.services_submitted


def test_from_status_services_failed_is_empty_on_success():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    assert result.services_failed == {}


# ---------------------------------------------------------------------------
# AnalysisResult — dynamic service access

def test_service_attributes_are_service_results():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    assert isinstance(result.nudenet, ServiceResult)
    assert isinstance(result.colors, ServiceResult)


def test_services_namespace_exposes_service_results():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    assert result.services.nudenet is result.nudenet
    assert result.services.colors is result.colors
    assert "nudenet" in result.services.names()


def test_service_data_is_accessible():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    assert result.nudenet.detections == []
    assert result.colors.dominant == ["#ffffff"]


def test_missing_service_returns_none():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    assert result.yolo is None
    assert result.nonexistent_service is None


def test_private_attributes_raise_attribute_error():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    with pytest.raises(AttributeError):
        _ = result._nonexistent_private


def test_service_result_processing_time_from_status():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    assert result.nudenet.processing_time == 0.4


def test_nsfw_detections_returns_filtered_nudenet_predictions():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    result.nudenet._data["predictions"] = [
        {"label": "FEMALE_BREAST_EXPOSED", "confidence": 0.9},
        {"label": "BELLY_EXPOSED", "confidence": 0.99},
        {"label": "FEMALE_GENITALIA_EXPOSED", "confidence": 0.4},
    ]
    assert result.nsfw_detections() == [
        {"label": "FEMALE_BREAST_EXPOSED", "confidence": 0.9},
    ]


def test_has_nsfw_true_when_flagged_detections_present():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    result.nudenet._data["predictions"] = [
        {"label": "FEMALE_BREAST_EXPOSED", "confidence": 0.9},
    ]
    assert result.has_nsfw() is True


def test_has_nsfw_false_without_nudenet():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    result._service_results.pop("nudenet")
    assert result.has_nsfw() is False


# ---------------------------------------------------------------------------
# AnalysisResult — partial failure warning

def test_from_status_warns_on_failed_services():
    import copy
    partial = copy.deepcopy(STATUS_COMPLETE)
    partial["services_failed"] = {"nudenet": "worker crashed"}
    partial["service_results"].pop("nudenet")

    with pytest.warns(UserWarning, match="nudenet"):
        result = AnalysisResult._from_status(partial)

    assert result.nudenet is None
    assert result.colors is not None


def test_from_status_preserves_terminal_failure_metadata_when_data_is_null():
    with pytest.warns(UserWarning, match="pose"):
        result = AnalysisResult._from_status(STATUS_COMPLETE_WITH_TERMINAL_FAILURE)

    assert result.pose is not None
    assert result.pose.status == "failed"
    assert result.pose.error_message == "worker returned terminal failure"
    assert result.pose.processing_time == 0.3


# ---------------------------------------------------------------------------
# AnalysisResult — repr

def test_repr_includes_image_id():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    assert "42" in repr(result)


# ---------------------------------------------------------------------------
# AnalysisResult — to_dict / to_json

def test_to_dict_has_top_level_fields():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    d = result.to_dict()
    assert d["image_id"] == 42
    assert d["services_submitted"] == STATUS_COMPLETE["services_submitted"]
    assert d["services_failed"] == {}


def test_to_dict_includes_image_meta():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    d = result.to_dict()
    assert d["image_filename"] == "test.png"
    assert "image_created" in d
    assert "image_group" not in d


def test_image_meta_as_attributes():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    assert result.image_filename == "test.png"
    assert result.image_created == "2026-03-08T12:00:00"


def test_image_meta_none_in_partial():
    result = AnalysisResult._from_partial(1, {})
    assert result.image_filename is None
    assert result.image_created is None


def test_to_dict_services_are_nested():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    d = result.to_dict()
    assert "services" in d
    assert "nudenet" in d["services"]
    assert "nudenet" not in d  # not flat at top level


def test_to_dict_strips_service_and_status_fields():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    d = result.to_dict()
    for service_data in d["services"].values():
        assert "service" not in service_data
        assert "status" not in service_data


def test_to_dict_service_data_matches_service_result():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    d = result.to_dict()
    expected = {k: v for k, v in result.nudenet._data.items()
                if k not in ("service", "status")}
    assert d["services"]["nudenet"] == expected


def test_to_json_returns_valid_json():
    import json
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    parsed = json.loads(result.to_json())
    assert parsed["image_id"] == 42


def test_to_json_accepts_indent():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    pretty = result.to_json(indent=2)
    assert "\n" in pretty


def test_caption_prefers_caption_summary():
    result = AnalysisResult._from_status(STATUS_COMPLETE_BASIC)
    assert result.caption == "A dog is sitting on a hardwood floor."


def test_caption_falls_back_to_first_text_service():
    result = AnalysisResult._from_status(STATUS_COMPLETE_BASIC)
    result._service_results.pop("caption_summary", None)
    assert result.caption == "a dog sitting on a wooden floor"


def test_scene_is_derived_from_content_analysis():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    assert result.scene is not None
    assert result.scene.type == "safe"
    assert result.scene.intimacy == "none"
    assert result.scene.activities == []
    assert result.scene.activity is None


def test_scene_activity_returns_single_activity_only():
    import copy
    status = copy.deepcopy(STATUS_COMPLETE)
    result = AnalysisResult._from_status(status)
    result.content_analysis._data["full_analysis"]["activity_analysis"]["activities"] = ["oral_sex"]
    assert result.scene.activity == "oral_sex"


def test_scene_uses_activities_detected_fallback():
    import copy
    status = copy.deepcopy(STATUS_COMPLETE)
    result = AnalysisResult._from_status(status)
    result.content_analysis._data["full_analysis"]["activity_analysis"].pop("activities", None)
    result.content_analysis._data["full_analysis"]["activity_analysis"]["activities_detected"] = ["kissing"]
    assert result.scene.activities == ["kissing"]
    assert result.scene.activity == "kissing"


def test_is_nsfw_false_when_nudenet_present_without_flags():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    assert result.is_nsfw is False
    assert result.is_safe is True

def test_is_nsfw_true_when_flagged_detections_present():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    result.nudenet._data["predictions"] = [
        {"label": "FEMALE_BREAST_EXPOSED", "confidence": 0.9},
    ]
    assert result.is_nsfw is True
    assert result.is_safe is False


def test_is_nsfw_none_without_moderation_signals():
    result = AnalysisResult._from_partial(1, {})
    assert result.is_nsfw is None
    assert result.is_safe is None


def test_reason_describes_flagged_detections():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    result.nudenet._data["predictions"] = [
        {"label": "FEMALE_BREAST_EXPOSED", "confidence": 0.9},
    ]
    assert "FEMALE_BREAST_EXPOSED" in result.moderation.reason


def test_reason_uses_content_analysis_when_safe():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    assert result.moderation.reason == "Content analysis: scene=safe, intimacy=none."


def test_reason_reports_missing_signal_when_unknown():
    result = AnalysisResult._from_partial(1, {})
    assert result.moderation.reason == "No moderation signal is available on this result."


# ---------------------------------------------------------------------------
# AnalysisResult — unwrapped service results (noun_consensus, caption_summary)

def test_noun_consensus_accessible_as_attribute():
    result = AnalysisResult._from_status(STATUS_COMPLETE_BASIC)
    assert result.noun_consensus is not None


def test_noun_consensus_nouns_readable():
    result = AnalysisResult._from_status(STATUS_COMPLETE_BASIC)
    nouns = result.noun_consensus.nouns
    assert len(nouns) == 1
    assert nouns[0]["canonical"] == "dog"


def test_noun_consensus_grounding_validated():
    result = AnalysisResult._from_status(STATUS_COMPLETE_BASIC)
    assert result.noun_consensus.nouns[0]["grounding_validated"] is True


def test_nouns_namespace_exposes_consensus_and_validated_lists():
    result = AnalysisResult._from_status(STATUS_COMPLETE_BASIC)
    assert result.nouns is not None
    assert [noun["canonical"] for noun in result.nouns.consensus] == ["dog", "floor"]
    assert [noun["canonical"] for noun in result.nouns.validated] == ["dog"]


def test_nouns_regions_exposes_grounding_predictions():
    result = AnalysisResult._from_status(STATUS_COMPLETE_BASIC)
    assert result.nouns is not None
    assert result.nouns.regions == [
        {"label": "dog", "bbox": {"x": 50, "y": 80, "width": 200, "height": 180}},
    ]


def test_verbs_namespace_none_when_no_verb_consensus():
    result = AnalysisResult._from_status(STATUS_COMPLETE_BASIC)
    assert result.verbs is None


def test_caption_summary_accessible_as_attribute():
    result = AnalysisResult._from_status(STATUS_COMPLETE_BASIC)
    assert result.caption_summary is not None


def test_caption_summary_text_readable():
    result = AnalysisResult._from_status(STATUS_COMPLETE_BASIC)
    assert result.caption_summary.summary_caption == "A dog is sitting on a hardwood floor."


def test_vlm_text_property_on_basic_result():
    result = AnalysisResult._from_status(STATUS_COMPLETE_BASIC)
    assert result.moondream.text == "a dog sitting on a wooden floor"


# ---------------------------------------------------------------------------
# rembg injection from top-level key

def test_rembg_injected_from_top_level():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    assert result.rembg is not None


def test_rembg_data_accessible():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    assert result.rembg.png_b64 == "aGVsbG8="
    assert result.rembg.shape == [512, 512]
    assert result.rembg.model is not None


def test_rembg_absent_when_null():
    import copy
    data = copy.deepcopy(STATUS_COMPLETE)
    data["rembg"] = None
    result = AnalysisResult._from_status(data)
    assert result.rembg is None




# ---------------------------------------------------------------------------
# Multi-cluster postprocessing aggregation (e.g. colors_post)

def test_multi_cluster_predictions_include_cluster_id():
    import copy
    data = copy.deepcopy(STATUS_COMPLETE)
    data["postprocessing"] = [
        {"service": "colors_post", "data": {"cluster_id": "grounding_dog",    "predictions": [{"hex": "#ff0000"}]}},
        {"service": "colors_post", "data": {"cluster_id": "grounding_woman",  "predictions": [{"hex": "#00ff00"}]}},
    ]
    result = AnalysisResult._from_status(data)
    preds = result.colors_post.predictions
    assert len(preds) == 2
    assert preds[0]["cluster_id"] == "grounding_dog"
    assert preds[1]["cluster_id"] == "grounding_woman"


def test_multi_cluster_predictions_without_cluster_id_unchanged():
    import copy
    data = copy.deepcopy(STATUS_COMPLETE)
    data["postprocessing"] = [
        {"service": "face", "data": {"predictions": [{"label": "face", "confidence": 0.9}]}},
        {"service": "face", "data": {"predictions": [{"label": "face", "confidence": 0.8}]}},
    ]
    result = AnalysisResult._from_status(data)
    preds = result.face.predictions
    assert len(preds) == 2
    assert "cluster_id" not in preds[0]


# ---------------------------------------------------------------------------
def test_to_dict_does_not_include_internal_api_fields():
    result = AnalysisResult._from_status(STATUS_COMPLETE)
    d = result.to_dict()
    for internal in ("service_dispatch", "downstream_pending", "primary_complete",
                     "consensus_complete", "vlm_services", "progress"):
        assert internal not in d


def test_to_dict_preserves_terminal_failure_error_message():
    with pytest.warns(UserWarning, match="pose"):
        result = AnalysisResult._from_status(STATUS_COMPLETE_WITH_TERMINAL_FAILURE)

    service_dict = result.to_dict()["services"]["pose"]
    assert service_dict["error_message"] == "worker returned terminal failure"


def test_current_api_status_fixture_parses_without_drift():
    data = _load_fixture("current_api_status.json")
    result = AnalysisResult._from_status(data)

    assert result.image_id == 4242
    assert result.noun_consensus is not None
    assert result.caption_summary is not None
    assert result.content_analysis is not None
    assert result.rembg is not None
    assert result.colors_post is not None
    assert len(result.colors_post.predictions) == 2
    assert result.colors_post.predictions[0]["cluster_id"] == "grounding_dog"
    assert result.to_dict()["services"]["content_analysis"]["analysis_version"] == "1.0"
