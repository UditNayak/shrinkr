from sqlalchemy import select

from app.db import SessionLocal
from app.models import Link
from tests.helpers import auth, create


def follow(client, code):
    return client.get(f"/{code}", follow_redirects=False)


def patch(client, link, **changes):
    return client.patch(f"/api/links/{link['code']}", json=changes, headers=auth(link))


def test_only_a_hash_of_the_token_is_stored(client):
    link = create(client)
    with SessionLocal() as session:
        stored = session.scalar(select(Link.token_hash).where(Link.code == link["code"]))
    assert stored != link["manage_token"] and len(stored) == 64  # SHA-256 in hex


def test_needs_the_links_own_token(client):
    link, other = create(client), create(client)
    path = f"/api/links/{link['code']}"
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 403
    assert client.get(path, headers=auth(other)).status_code == 403
    assert client.get(path, headers=auth(link)).status_code == 200


def test_editing_the_target_takes_effect_immediately(client):
    link = create(client)
    follow(client, link["code"])  # now cached in Redis
    assert patch(client, link, url="https://example.org/new").status_code == 200
    assert follow(client, link["code"]).headers["location"] == "https://example.org/new"


def test_disable_and_enable(client):
    link = create(client)
    patch(client, link, is_disabled=True)
    assert follow(client, link["code"]).status_code == 410
    patch(client, link, is_disabled=False)
    assert follow(client, link["code"]).status_code == 302


def test_delete(client):
    link = create(client, alias="delete-me")
    assert client.delete("/api/links/delete-me", headers=auth(link)).status_code == 204
    assert follow(client, "delete-me").status_code == 404
    assert create(client, alias="delete-me")["code"] == "delete-me"  # the alias is free again
