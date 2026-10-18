import pytest

from app import main
from tests.helpers import create, expire_now, in_future, run_worker, stats


def follow(client, code):
    return client.get(f"/{code}", follow_redirects=False)


def test_create_redirect_and_count(client):
    link = create(client)
    assert len(link["code"]) == 7
    assert link["short_url"].endswith("/" + link["code"])

    for _ in range(2):
        response = follow(client, link["code"])
        assert response.status_code == 302
        assert response.headers["location"] == link["target_url"]

    run_worker()
    assert stats(client, link)["clicks"] == 2


def test_unknown_code_returns_404(client):
    assert follow(client, "nope123").status_code == 404


@pytest.mark.parametrize("url", ["not a url", "ftp://example.com/"])
def test_rejects_invalid_urls(client, url):
    assert client.post("/api/links", json={"url": url}).status_code == 422


def test_custom_alias(client):
    link = create(client, alias="k8s-notes")
    assert link["code"] == "k8s-notes" and link["is_custom"] is True
    assert follow(client, "k8s-notes").headers["location"] == link["target_url"]


def test_taken_alias_returns_409(client):
    create(client, alias="taken-alias")
    response = client.post("/api/links", json={"url": "https://example.org/", "alias": "taken-alias"})
    assert response.status_code == 409


@pytest.mark.parametrize("alias", ["ab", "has space", "docs"])
def test_rejects_bad_aliases(client, alias):
    response = client.post("/api/links", json={"url": "https://example.com/", "alias": alias})
    assert response.status_code == 422


def test_retries_on_code_collision(client, monkeypatch):
    first = create(client)
    codes = iter([first["code"], "fresh01"])
    monkeypatch.setattr(main, "generate_code", lambda: next(codes))
    assert create(client)["code"] == "fresh01"


def test_link_stops_after_max_clicks(client):
    link = create(client, max_clicks=2)
    assert [follow(client, link["code"]).status_code for _ in range(3)] == [302, 302, 410]
    assert stats(client, link)["clicks"] == 2


def test_expired_link_returns_410(client):
    link = create(client, expires_at=in_future(days=1))
    expire_now(link["code"])
    assert follow(client, link["code"]).status_code == 410


@pytest.mark.parametrize("expires_at", ["2000-01-01T00:00:00Z", "2999-01-01T00:00:00"])
def test_rejects_bad_expiry(client, expires_at):
    response = client.post("/api/links", json={"url": "https://example.com/", "expires_at": expires_at})
    assert response.status_code == 422
