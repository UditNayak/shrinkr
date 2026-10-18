"""QR code images for short links."""

import io

import segno

MEDIA_TYPES = {"svg": "image/svg+xml", "png": "image/png"}
QUIET_ZONE = 4  # blank border, in modules; the QR standard asks for 4 so scanners find the edges


def render(text: str, image_format: str, scale: int) -> tuple[bytes, str]:
    """The QR code for `text` as (image bytes, media type).

    error="m": up to ~15% of the code can be damaged or covered and it still scans.
    segno raises the level automatically when a stronger one fits in the same size.
    """
    qr = segno.make(text, error="m", micro=False)
    buffer = io.BytesIO()
    qr.save(buffer, kind=image_format, scale=scale, border=QUIET_ZONE)
    return buffer.getvalue(), MEDIA_TYPES[image_format]
