import io

import segno

MEDIA_TYPES = {"svg": "image/svg+xml", "png": "image/png"}


def render(text: str, image_format: str, scale: int) -> tuple[bytes, str]:
    qr = segno.make(text, error="m", micro=False)
    buffer = io.BytesIO()
    qr.save(buffer, kind=image_format, scale=scale, border=4)  # 4 = standard quiet zone
    return buffer.getvalue(), MEDIA_TYPES[image_format]
