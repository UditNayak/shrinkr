import pytest


def shorten(client, url):
    return client.post("/api/links", json={"url": url})


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8080/admin",
        "http://192.168.1.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://2130706433/",  # 127.0.0.1 as a number
        "https://paypal.com@evil.example/",  # really goes to evil.example
        "http://testserver/abc1234",  # shrinkr itself
        "https://bit.ly/abc",
    ],
)
def test_blocks_unsafe_targets(client, url):
    assert shorten(client, url).status_code == 422


@pytest.mark.parametrize("url", ["https://example.com/", "https://notbit.ly/"])
def test_allows_public_targets(client, url):
    assert shorten(client, url).status_code == 201
