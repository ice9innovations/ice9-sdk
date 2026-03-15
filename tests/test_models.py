import pytest

from ice9.models import AnalysisResult, ServiceResult

from .conftest import STATUS_COMPLETE, STATUS_COMPLETE_BASIC


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
