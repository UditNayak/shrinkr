import io

import segno

from tests.helpers import create


def test_encodes_the_short_url(client):
    link = create(client)
    response = client.get(f"/api/links/{link['code']}/qr")
    assert response.headers["content-type"] == "image/svg+xml"
    # Byte-for-byte what segno makes for the short URL: so that's what a scan reads.
    expected = io.BytesIO()
    segno.make(link["short_url"], error="m", micro=False).save(expected, kind="svg", scale=10, border=4)
    assert response.content == expected.getvalue()


def test_png_on_request(client):
    link = create(client)
    response = client.get(f"/api/links/{link['code']}/qr", params={"format": "png"})
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")  # the PNG file signature


def test_unknown_link_has_no_qr_code(client):
    assert client.get("/api/links/nope123/qr").status_code == 404
