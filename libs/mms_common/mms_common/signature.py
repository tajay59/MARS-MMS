"""A drawn signature and the name typed with it (TRD 11.3; PRD RPT-4, REQ-13). No I/O.

Shared by the report service (technicians sign visit reports) and operations (a client signs
their acceptance of the work), so both check a signature the same way.
"""

from __future__ import annotations

import base64
import binascii
import struct

from mms_common.errors import ValidationFailed

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PNG_END = b"IEND\xaeB`\x82"
NAME_MIN, NAME_MAX = 2, 120


def png_bytes(
    image: str, *, max_bytes: int, max_width: int, max_height: int
) -> tuple[bytes, int, int]:
    """Decode a drawn signature (base64, or a `data:image/png;base64,` URI) and check it: PNG
    magic bytes and end marker, at most `max_bytes`, at most `max_width` x `max_height` pixels.
    Returns the bytes and the size."""
    encoded = image.split(",", 1)[1] if image.startswith("data:") else image
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValidationFailed("The signature is not a valid image", code="bad_signature",
                               field="image") from e
    if not raw.startswith(PNG_MAGIC) or not raw.endswith(PNG_END) or len(raw) < 33:
        raise ValidationFailed("The signature must be a PNG image", code="bad_signature",
                               field="image")
    if len(raw) > max_bytes:
        raise ValidationFailed(f"The signature image is too large (at most {max_bytes // 1024} KB)",
                               code="signature_too_large", field="image")
    # The first chunk is IHDR: length(4) "IHDR"(4) width(4) height(4)
    if raw[12:16] != b"IHDR":
        raise ValidationFailed("The signature must be a PNG image", code="bad_signature",
                               field="image")
    width, height = struct.unpack(">II", raw[16:24])
    if not (0 < width <= max_width and 0 < height <= max_height):
        raise ValidationFailed(
            f"The signature image is too big (at most {max_width} x {max_height} pixels)",
            code="signature_too_large", field="image")
    return raw, width, height


def typed_name(value: str) -> str:
    name = " ".join(value.split())
    if not NAME_MIN <= len(name) <= NAME_MAX:
        raise ValidationFailed(f"Type your full name ({NAME_MIN} to {NAME_MAX} characters)",
                               code="bad_name", field="typed_name")
    return name
