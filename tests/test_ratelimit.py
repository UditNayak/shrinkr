from app import ratelimit


def shorten(client):
    return client.post("/api/links", json={"url": "https://example.com/"})


def test_create_is_limited_per_minute(client, monkeypatch):
    monkeypatch.setattr(ratelimit.create_limit, "limit", 2)
    assert [shorten(client).status_code for _ in range(3)] == [201, 201, 429]
    assert 1 <= int(shorten(client).headers["retry-after"]) <= 60


def test_fails_open_when_redis_is_down(client, fake_redis, monkeypatch):
    monkeypatch.setattr(ratelimit.create_limit, "limit", 1)
    fake_redis.connected = False
    assert [shorten(client).status_code for _ in range(3)] == [201, 201, 201]
