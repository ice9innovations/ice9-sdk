"""Image upload metadata detection shared by sync and async clients."""

from __future__ import annotations

import io
from pathlib import Path
from typing import BinaryIO

from .exceptions import ImageRejectedError


SUPPORTED_IMAGES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
}


def detect_image_type(header: bytes) -> tuple[str, str] | None:
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp", ".webp"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        brands = {header[offset:offset + 4] for offset in range(8, len(header) - 3, 4) if offset != 12}
        if brands & {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis"}:
            return "image/heic", ".heic"
        if not brands & {b"avif", b"avis"} and brands & {b"mif1", b"msf1"}:
            return "image/heif", ".heif"
    return None


def prepare_upload(
    fileobj: BinaryIO,
    filename: str,
    media_type: str | None = None,
) -> tuple[BinaryIO, str, str]:
    try:
        position = fileobj.tell()
        header = fileobj.read(64)
        fileobj.seek(position)
        upload = fileobj
    except (AttributeError, OSError, io.UnsupportedOperation):
        header = fileobj.read(64)
        upload = io.BytesIO(header + fileobj.read())

    detected = detect_image_type(header)
    if detected is None:
        raise ImageRejectedError(
            "Could not identify image bytes. Supported in-memory formats are JPEG, PNG, WebP, HEIC, and HEIF."
        )
    detected_type, extension = detected
    if media_type is not None and media_type not in SUPPORTED_IMAGES:
        raise ImageRejectedError(
            f"Unsupported media_type {media_type!r}. Supported types are JPEG, PNG, WebP, HEIC, and HEIF."
        )
    if media_type is not None and media_type != detected_type:
        raise ImageRejectedError(
            f"The supplied media_type {media_type} does not match the detected {detected_type} image."
        )

    safe_name = Path(str(filename or "upload")).name
    canonical_name = f"{Path(safe_name).stem or 'upload'}{extension}"
    return upload, canonical_name, detected_type
