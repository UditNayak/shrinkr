from sqlalchemy import update

from app import redis_conn
from app.db import SessionLocal
from app.events import STREAM
from app.models import Link
from tests.helpers import create, stats


def follow(client, code):
    return client.get(f"/{code}", follow_redirects=False)


def test_cached_redirects_do_not_read_the_database(client):
    link = create(client)
    follow(client, link["code"])
    # change the target directly in the database, so the cache isn't told
    with SessionLocal() as session:
        session.execute(update(Link).where(Link.code == link["code"]).values(target_url="https://example.org/x"))
        session.commit()
    assert follow(client, link["code"]).headers["location"] == link["target_url"]
    assert redis_conn.redis_client.xlen(STREAM) == 2


def test_click_limited_links_skip_the_cache(client):
    link = create(client, max_clicks=5)
    follow(client, link["code"])
    assert redis_conn.redis_client.get(f"link:{link['code']}") is None
    assert stats(client, link)["clicks"] == 1


def test_redirects_work_without_redis(client, fake_redis):
    link = create(client)
    fake_redis.connected = False
    response = follow(client, link["code"])
    assert response.status_code == 302
    fake_redis.connected = True
    assert stats(client, link)["clicks"] == 1
