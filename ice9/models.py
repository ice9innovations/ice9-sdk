from __future__ import annotations

import json
import warnings

# Fields copied from the raw API response into to_dict() output.
_RESULT_META_FIELDS = ("image_filename", "image_group", "image_created")

# Fields stripped from service data before serialisation — pipeline bookkeeping
# that is already captured at the top level or is not meaningful to callers.
_SERVICE_STRIP_FIELDS = frozenset({"service", "status"})


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
    ):
        self.image_id = image_id
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

        The raw API response is available at ``._raw`` if you need fields
        that this method omits.
        """
        service_results = object.__getattribute__(self, '_service_results')
        raw = object.__getattribute__(self, '_raw')

        out: dict = {
            "image_id":           self.image_id,
            "services_submitted": self.services_submitted,
            "services_failed":    self.services_failed,
        }
        for field in _RESULT_META_FIELDS:
            if field in raw:
                out[field] = raw[field]

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

    def censor(self, image, *, method="fill", labels=None, min_confidence=0.5, output=None):
        """Draw censoring over nudenet detections on the original image.

        Returns a PIL Image. See ice9.censor for full documentation.
        """
        from .censor import censor as _censor
        return _censor(self, image, method=method, labels=labels,
                       min_confidence=min_confidence, output=output)

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
                data=entry.get('data') if 'data' in entry else entry,
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
                    data=entry,
                    processing_time=entry.get('processing_time'),
                )

        # Inject postprocessing entries that aren't already in service_results.
        # Postprocessing entries share the same shape as service_results entries
        # but arrive in a flat list keyed by a "service" field. Multiple entries
        # for the same service name (e.g. one face entry per detected cluster)
        # are aggregated by merging their predictions lists.
        postprocessing = data.get('postprocessing') or []
        if postprocessing:
            # caption_score_* entries are aggregated into a single caption_scores
            # ServiceResult: {"blip": 0.847, "moondream": 0.831, ...}
            caption_scores: dict[str, float] = {}
            pp_groups: dict[str, list[dict]] = {}

            for entry in postprocessing:
                name = entry.get('service')
                if not name:
                    continue
                if name.startswith('caption_score_'):
                    model = name[len('caption_score_'):]
                    entry_data = entry.get('data') if 'data' in entry else entry
                    score = (entry_data.get('caption_score') or {}).get('similarity_score')
                    if score is not None:
                        caption_scores[model] = score
                else:
                    pp_groups.setdefault(name, []).append(entry)

            if caption_scores and 'caption_scores' not in service_results:
                service_results['caption_scores'] = ServiceResult(data=caption_scores)

            for name, entries in pp_groups.items():
                if name in service_results:
                    continue  # don't overwrite existing service_results

                if len(entries) == 1:
                    entry = entries[0]
                    entry_data = entry.get('data') if 'data' in entry else entry
                    service_results[name] = ServiceResult(
                        data=entry_data,
                        processing_time=entry.get('processing_time'),
                    )
                else:
                    # Aggregate predictions from all entries for this service
                    all_predictions = []
                    for entry in entries:
                        entry_data = entry.get('data') if 'data' in entry else entry
                        all_predictions.extend(entry_data.get('predictions') or [])
                    service_results[name] = ServiceResult(
                        data={'predictions': all_predictions},
                    )

        return cls(
            image_id=data['image_id'],
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
        service_results = {
            name: ServiceResult(
                data=entry.get('data') if 'data' in entry else entry,
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
