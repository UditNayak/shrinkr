import pytest


def shorten(client, url):
    return client.post("/api/links", json={"url": url})


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8080/admin",  # this machine
        "http://192.168.1.1/admin",  # private network (home router)
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata service
        "http://2130706433/",  # 127.0.0.1 written as one number
        "https://paypal.com@evil.example/",  # "username" trick: really goes to evil.example
        "http://testserver/abc1234",  # shrinkr itself (the test client's host): redirect loops
        "https://bit.ly/abc",  # another shortener: hides the destination
    ],
)
def test_blocks_unsafe_targets(client, url):
    assert shorten(client, url).status_code == 422


@pytest.mark.parametrize("url", ["https://example.com/", "https://notbit.ly/"])  # look-alike must pass
def test_allows_public_targets(client, url):
    assert shorten(client, url).status_code == 201
