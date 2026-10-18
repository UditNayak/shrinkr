from datetime import UTC, datetime

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import DailyClicks, Link
from tests.helpers import auth, create, run_worker


def follow(client, code):
    return client.get(f"/{code}", follow_redirects=False)


def get_stats(client, link, days=7):
    response = client.get(f"/api/links/{link['code']}/stats", headers=auth(link), params={"days": days})
    assert response.status_code == 200
    return response.json()


def test_clicks_per_day(client):
    link = create(client)
    for _ in range(3):
        follow(client, link["code"])
    run_worker()

    stats = get_stats(client, link, days=7)
    assert stats["total_clicks"] == 3
    assert len(stats["daily"]) == 7
    assert stats["daily"][-1] == {"day": datetime.now(UTC).date().isoformat(), "clicks": 3}
    assert sum(day["clicks"] for day in stats["daily"]) == 3


def test_click_limited_links_are_counted_once(client):
    link = create(client, max_clicks=10)
    follow(client, link["code"])
    run_worker()
    stats = get_stats(client, link)
    assert stats["total_clicks"] == 1 and stats["daily"][-1]["clicks"] == 1


def test_deleting_a_link_deletes_its_stats(client):
    link = create(client)
    follow(client, link["code"])
    run_worker()
    with SessionLocal() as session:
        link_id = session.scalar(select(Link.id).where(Link.code == link["code"]))
    client.delete(f"/api/links/{link['code']}", headers=auth(link))

    with SessionLocal() as session:
        rows = session.scalar(select(func.count()).select_from(DailyClicks).where(DailyClicks.link_id == link_id))
    assert rows == 0
