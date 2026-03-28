from __future__ import annotations

import json
import warnings

from .censor import CENSOR_LABELS

# Fields stripped from service data before serialisation — pipeline bookkeeping
# that is already captured at the top level or is not meaningful to callers.
_SERVICE_STRIP_FIELDS = frozenset({"service", "status"})


def _unwrap_service_entry(entry: dict) -> dict:
    """Return a service payload suitable for ServiceResult.

    The API may return terminal failed artifacts as:

        {"status": "failed", "error_message": "...", "data": None}

    Preserve that terminal metadata instead of collapsing the entry to an
    empty dict just because the structured ``data`` payload is null.
    """
    if not isinstance(entry, dict):
        return entry or {}

    if 'data' not in entry:
        return entry

    data = entry.get('data')
    metadata = {
        key: value
        for key, value in entry.items()
        if key not in {'data', 'processing_time'}
    }

    if isinstance(data, dict):
        return {**metadata, **data}

    if data is None:
        return metadata

    return {**metadata, 'value': data}


class ServiceResult:
    """Wraps a service's result data dict with attribute access.

    Use attribute access for known fields::

        result.nudenet.detections
        result.colors.dominant

    The underlying dict is available at ``._data`` if you need to iterate
    keys or handle fields the SDK doesn't know about yet.
    """

    def __init__(self, data: dict, processing_time: float | None = None):
        object.__setattr__(self, '_data', data or {})
        object.__setattr__(self, 'processing_time', processing_time)

    def __getattr__(self, name: str):
        data = object.__getattribute__(self, '_data')
        try:
            return data[name]
        except KeyError:
            raise AttributeError(
                f"{type(self).__name__!r} has no attribute {name!r}. "
                f"Available keys: {list(data.keys())}"
            )

    def __repr__(self) -> str:
        data = object.__getattribute__(self, '_data')
        return f"ServiceResult({list(data.keys())})"

    @property
    def predictions(self) -> list:
        """Predictions list for detection and grounding services.

        Returns ``_data["predictions"]`` if present, ``[]`` otherwise.
        Always a list — safe to iterate without a guard::

            for p in result.nudenet.predictions:
                print(p["label"], p["confidence"])
        """
        data = object.__getattribute__(self, '_data')
        return data.get("predictions") or []

    @property
    def text(self) -> str | None:
        """Primary text output for VLM services.

        Returns ``predictions[0]["text"]`` if present, ``None`` otherwise.
        Non-VLM services (nudenet, colors, etc.) return ``None`` silently.
        """
        data = object.__getattribute__(self, '_data')
        predictions = data.get("predictions") or []
        if predictions:
            return predictions[0].get("text")
        return None

    def __bool__(self) -> bool:
        return bool(object.__getattribute__(self, '_data'))

    def flagged_predictions(
        self,
        *,
        labels: frozenset[str] | set[str] | None = None,
        min_confidence: float = 0.5,
    ) -> list[dict]:
        """Return predictions matching the given labels and confidence floor.

        This is primarily useful for moderation-oriented services like
        ``nudenet``. By default it uses ``CENSOR_LABELS`` so callers can treat
        the result as a ready-to-use NSFW screening set.
        """
        effective_labels = labels if labels is not None else CENSOR_LABELS
        return [
            prediction
            for prediction in self.predictions
            if prediction.get("label") in effective_labels
            and prediction.get("confidence", 0) >= min_confidence
        ]


class ModerationResult:
    """Moderation-oriented helpers for an AnalysisResult."""

    def __init__(self, result: "AnalysisResult"):
        self._result = result

    @property
    def reason(self) -> str:
        """Return a short human-readable explanation of the moderation signal."""
        result = self._result
        detections = result.nsfw_detections()
        if detections:
            labels = ", ".join(sorted({d.get("label", "unknown") for d in detections}))
            return f"Flagged NudeNet detections: {labels}."

        if result.content_analysis is not None:
            scene = result.scene
            if scene:
                parts = []
                if scene.type is not None:
                    parts.append(f"scene={scene.type}")
                if scene.intimacy is not None:
                    parts.append(f"intimacy={scene.intimacy}")
                if scene.activities:
                    parts.append(f"activities={','.join(map(str, scene.activities))}")
                if parts:
                    return "Content analysis: " + ", ".join(parts) + "."

        if result.nudenet is not None:
            return "No flagged NudeNet detections above the default threshold."

        return "No moderation signal is available on this result."

    def censor(self, image, *, method="fill", labels=None, min_confidence=0.5, output=None):
        """Draw censoring over nudenet detections on the original image."""
        from .censor import censor as _censor
        return _censor(
            self._result,
            image,
            method=method,
            labels=labels,
            min_confidence=min_confidence,
            output=output,
        )


class SceneResult:
    """Product-shaped scene summary derived from content_analysis."""

    def __init__(
        self,
        *,
        type: str | None = None,
        intimacy: str | None = None,
        activities: list[str] | None = None,
        anatomy_exposed: list[str] | None = None,
        raw: dict | None = None,
    ):
        self.type = type
        self.intimacy = intimacy
        self.activities = sorted(activities or [])
        self.anatomy_exposed = anatomy_exposed or []
        self.raw = raw or {}

    def __bool__(self) -> bool:
        return any((
            self.type is not None,
            self.intimacy is not None,
            bool(self.activities),
            bool(self.anatomy_exposed),
        ))

    @property
    def activity(self) -> str | None:
        """Return the single detected activity when the worker produced one."""
        if len(self.activities) == 1:
            return self.activities[0]
        return None

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "intimacy": self.intimacy,
            "activity": self.activity,
            "activities": self.activities,
            "anatomy_exposed": self.anatomy_exposed,
        }


class NounsResult:
    """Noun-oriented helpers for an AnalysisResult."""

    def __init__(self, result: "AnalysisResult"):
        self._result = result

    @property
    def consensus(self) -> list[dict]:
        noun_consensus = self._result.noun_consensus
        if noun_consensus is None:
            return []
        return noun_consensus._data.get("nouns_all") or noun_consensus._data.get("nouns") or []

    @property
    def validated(self) -> list[dict]:
        noun_consensus = self._result.noun_consensus
        if noun_consensus is None:
            return []
        return noun_consensus._data.get("nouns") or []

    @property
    def regions(self) -> list[dict]:
        grounding = self._result.florence2_grounding
        if grounding is None:
            return []
        return grounding.predictions

    def __bool__(self) -> bool:
        return bool(self.consensus or self.regions)


class VerbsResult:
    """Verb-oriented helpers for an AnalysisResult."""

    def __init__(self, result: "AnalysisResult"):
        self._result = result

    @property
    def consensus(self) -> list:
        verb_consensus = self._result.verb_consensus
        if verb_consensus is None:
            return []
        return verb_consensus._data.get("verbs") or []

    def __bool__(self) -> bool:
        return bool(self.consensus)


class ServicesResult:
    """Advanced access to underlying service outputs."""

    def __init__(self, service_results: dict[str, ServiceResult]):
        self._service_results = service_results

    def __getattr__(self, name: str) -> ServiceResult | None:
        if name.startswith('_'):
            raise AttributeError(name)
        return self._service_results.get(name)

    def __bool__(self) -> bool:
        return bool(self._service_results)

    def names(self) -> list[str]:
        return sorted(self._service_results.keys())


class AnalysisResult:
    """The result of a completed image analysis.

    Service results are accessed by name as attributes. Which services are
    present depends on which ran for this image — the API determines that,
    not the SDK. Any service that succeeded is available::

        result.nudenet    # content moderation
        result.colors     # dominant colors
        result.ocr        # extracted text
        result.metadata   # EXIF and file metadata
        result.qr         # QR/barcode detections

    Accessing a service that was not submitted or did not succeed returns None.

    Attributes:
        image_id:           Numeric ID assigned by the API.
        image_filename:     Original filename of the uploaded image, if available.
        image_created:      ISO 8601 timestamp when the image record was created.
        services_submitted: List of service names that were run.
        services_failed:    Dict of service -> failure reason. Empty = full success.
    """

    def __init__(
        self,
        image_id: int,
        services_submitted: list[str],
        services_failed: dict[str, str | None],
        service_results: dict[str, "ServiceResult"],
        _raw: dict,
        is_complete: bool = True,
        image_filename: str | None = None,
        image_created: str | None = None,
    ):
        self.image_id = image_id
        self.image_filename = image_filename
        self.image_created = image_created
        self.services_submitted = services_submitted
        self.services_failed = services_failed
        self.is_complete = is_complete
        self._service_results = service_results
        self._raw = _raw

    def __getattr__(self, name: str) -> "ServiceResult | None":
        # Attribute lookup falls through here only for names not set in __init__.
        # That means any service name the caller uses (result.nudenet, result.colors,
        # result.my_custom_service, etc.) resolves to the result or None.
        service_results = object.__getattribute__(self, '_service_results')
        if name.startswith('_'):
            raise AttributeError(name)
        return service_results.get(name)

    def to_dict(self) -> dict:
        """Return a clean dict representation of the result.

        Service results are nested under a ``services`` key so they can be
        iterated unambiguously. Pipeline bookkeeping fields (``service``,
        ``status``) are stripped from each service's data — that information
        is already present at the top level via ``services_submitted`` and
        ``services_failed``.
        """
        service_results = object.__getattribute__(self, '_service_results')

        out: dict = {
            "image_id":           self.image_id,
            "services_submitted": self.services_submitted,
            "services_failed":    self.services_failed,
        }
        if self.image_filename is not None:
            out["image_filename"] = self.image_filename
        if self.image_created is not None:
            out["image_created"] = self.image_created

        out["services"] = {
            name: {k: v for k, v in object.__getattribute__(sr, '_data').items()
                   if k not in _SERVICE_STRIP_FIELDS}
            for name, sr in service_results.items()
        }

        return out

    def to_json(self, **kwargs) -> str:
        """Serialise the result to a JSON string.

        Keyword arguments are forwarded to ``json.dumps``, so you can pass
        ``indent=2`` for pretty-printing.
        """
        return json.dumps(self.to_dict(), default=str, **kwargs)

    @property
    def raw(self) -> dict:
        """Return the raw API payload for advanced use cases."""
        return self._raw

    @property
    def services(self) -> ServicesResult:
        """Return advanced access to underlying service outputs."""
        return ServicesResult(self._service_results)

    @property
    def caption(self) -> str | None:
        """Return the best available image-level caption.

        Prefers the higher-level caption summary when present, then falls back
        to the first text-producing service result.
        """
        if self.caption_summary is not None:
            summary = self.caption_summary._data.get("summary_caption")
            if summary:
                return summary

        for service_name in self.services_submitted:
            service = self._service_results.get(service_name)
            if service is not None and service.text:
                return service.text
        return None

    @property
    def is_nsfw(self) -> bool | None:
        """Return a simple moderation decision for the image.

        Returns ``True`` when flagged NSFW detections are present, ``False``
        when moderation signals are available and clean, and ``None`` when no
        moderation signal is available on the result.
        """
        if self.has_nsfw():
            return True
        if self.nudenet is not None or self.content_analysis is not None:
            return False
        return None

    @property
    def scene(self) -> SceneResult | None:
        """Return a product-shaped scene summary from content_analysis."""
        if self.content_analysis is None:
            return None

        full_analysis = self.content_analysis._data.get("full_analysis") or {}
        activity = full_analysis.get("activity_analysis") or {}
        return SceneResult(
            type=activity.get("scene_type"),
            intimacy=activity.get("intimacy_level"),
            activities=activity.get("activities") or [],
            anatomy_exposed=full_analysis.get("anatomy_exposed") or [],
            raw=full_analysis,
        )

    @property
    def nouns(self) -> NounsResult | None:
        """Return noun-oriented helpers for this image."""
        nouns = NounsResult(self)
        return nouns if nouns else None

    @property
    def verbs(self) -> VerbsResult | None:
        """Return verb-oriented helpers for this image."""
        verbs = VerbsResult(self)
        return verbs if verbs else None

    @property
    def is_safe(self) -> bool | None:
        """Convenience inverse of ``is_nsfw`` when the result is classifiable."""
        value = self.is_nsfw
        if value is None:
            return None
        return not value

    @property
    def moderation(self) -> ModerationResult:
        """Return moderation-oriented helpers for this image."""
        return ModerationResult(self)

    def nsfw_detections(
        self,
        *,
        labels: frozenset[str] | set[str] | None = None,
        min_confidence: float = 0.5,
    ) -> list[dict]:
        """Return moderation detections from ``nudenet`` above the threshold.

        Higher tiers inherit the free-tier ``nudenet`` signal, so this helper
        gives all tiers a single moderation-oriented access pattern.
        """
        if self.nudenet is None:
            return []
        return self.nudenet.flagged_predictions(
            labels=labels,
            min_confidence=min_confidence,
        )

    def has_nsfw(
        self,
        *,
        labels: frozenset[str] | set[str] | None = None,
        min_confidence: float = 0.5,
    ) -> bool:
        """Return ``True`` when the result contains flagged NSFW detections."""
        return bool(self.nsfw_detections(labels=labels, min_confidence=min_confidence))

    def __repr__(self) -> str:
        service_results = object.__getattribute__(self, '_service_results')
        services = ', '.join(service_results.keys())
        return f"AnalysisResult(image_id={self.image_id}, services=[{services}])"

    @classmethod
    def _from_status(cls, data: dict) -> "AnalysisResult":
        raw_service_results = data.get('service_results') or {}
        services_failed = data.get('services_failed') or {}

        if services_failed:
            warnings.warn(
                f"Analysis completed with failed services: {list(services_failed.keys())}. "
                "Results for those services will be None.",
                stacklevel=4,
            )

        service_results = {
            name: ServiceResult(
                data=_unwrap_service_entry(entry),
                processing_time=entry.get('processing_time'),
            )
            for name, entry in raw_service_results.items()
        }

        # Inject top-level service keys that arrive outside service_results.
        # Currently: rembg (background removal matte). These keys are present
        # when the service ran and will be None otherwise — skip None values.
        for top_level_key in ('rembg',):
            if top_level_key not in service_results and data.get(top_level_key):
                entry = data[top_level_key]
                service_results[top_level_key] = ServiceResult(
                    data=_unwrap_service_entry(entry),
                    processing_time=entry.get('processing_time'),
                )

        # Inject postprocessing entries that aren't already in service_results.
        # Postprocessing entries share the same shape as service_results entries
        # but arrive in a flat list keyed by a "service" field. Multiple entries
        # for the same service name (e.g. one face entry per detected cluster)
        # are aggregated by merging their predictions lists.
        postprocessing = data.get('postprocessing') or []
        if postprocessing:
            pp_groups: dict[str, list[dict]] = {}

            for entry in postprocessing:
                name = entry.get('service')
                if not name:
                    continue
                pp_groups.setdefault(name, []).append(entry)

            for name, entries in pp_groups.items():
                if name in service_results:
                    continue  # don't overwrite existing service_results

                if len(entries) == 1:
                    entry = entries[0]
                    service_results[name] = ServiceResult(
                        data=_unwrap_service_entry(entry),
                        processing_time=entry.get('processing_time'),
                    )
                else:
                    # Aggregate predictions from all entries for this service.
                    # If an entry carries a cluster_id (e.g. colors_post, one per
                    # florence2 bounding box), embed it in each prediction so the
                    # UI can associate palettes with their source bounding box.
                    all_predictions = []
                    for entry in entries:
                        entry_data = _unwrap_service_entry(entry)
                        cluster_id = entry_data.get('cluster_id')
                        for pred in (entry_data.get('predictions') or []):
                            all_predictions.append(
                                {**pred, 'cluster_id': cluster_id} if cluster_id else pred
                            )
                    service_results[name] = ServiceResult(
                        data={'predictions': all_predictions},
                    )

        return cls(
            image_id=data['image_id'],
            image_filename=data.get('image_filename'),
            image_created=data.get('image_created'),
            services_submitted=data.get('services_submitted') or [],
            services_failed=services_failed,
            service_results=service_results,
            _raw=data,
        )

    @classmethod
    def _from_partial(cls, image_id: int, accumulated: dict) -> "AnalysisResult":
        """Build a partial result from accumulated service_complete SSE events.

        ``accumulated`` maps service name to the raw result entry from the
        ``service_complete`` event — same shape as ``service_results`` entries
        (wrapped or unwrapped, handled identically to ``_from_status``).
        """
        # postprocessing entries are aggregated into service_results by _stream()
        # before reaching here, so accumulated never contains raw postprocessing keys.
        service_results = {
            name: ServiceResult(
                data=_unwrap_service_entry(entry),
                processing_time=entry.get('processing_time'),
            )
            for name, entry in accumulated.items()
        }

        return cls(
            image_id=image_id,
            services_submitted=list(accumulated.keys()),
            services_failed={},
            service_results=service_results,
            _raw={},
            is_complete=False,
        )
