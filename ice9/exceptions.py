class Ice9Error(Exception):
    """Base exception for all ice9 SDK errors."""


class AuthError(Ice9Error):
    """API key is missing, invalid, or deactivated."""


class RateLimitError(Ice9Error):
    """Request rate limit exceeded. Retry after the indicated delay."""

    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after  # seconds, if server provided it


class ImageRejectedError(Ice9Error):
    """Server rejected the image (bad format, too large, empty, etc.)."""


class AnalysisTimeoutError(Ice9Error):
    """Analysis did not complete within the allowed timeout."""


class PartialResultError(Ice9Error):
    """Analysis completed but one or more services failed.

    The partial result is available on the `result` attribute.
    Services that succeeded are populated normally; failed services are None.
    """

    def __init__(self, message, result):
        super().__init__(message)
        self.result = result
