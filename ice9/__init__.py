from .client import Ice9
from .models import AnalysisResult, ServiceResult
from .censor import CENSOR_LABELS
from .exceptions import (
    Ice9Error,
    AuthError,
    RateLimitError,
    ImageRejectedError,
    AnalysisTimeoutError,
    PartialResultError,
)

__version__ = "0.0.1"

__all__ = [
    "Ice9",
    "AnalysisResult",
    "ServiceResult",
    "CENSOR_LABELS",
    "Ice9Error",
    "AuthError",
    "RateLimitError",
    "ImageRejectedError",
    "AnalysisTimeoutError",
    "PartialResultError",
]

# Async client is imported on-demand to avoid requiring httpx for sync usage
def __getattr__(name):
    if name == "AsyncIce9":
        from .async_client import AsyncIce9
        return AsyncIce9
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
