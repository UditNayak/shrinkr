from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.cleanup import purge_expired
from app.db import SessionLocal
from app.models import Link


def test_deletes_only_links_expired_beyond_the_grace_period():
    now = datetime.now(UTC)
    with SessionLocal() as session:
        for code, expires_at in [
            ("cleanup-old", now - timedelta(days=30)),
            ("cleanup-recent", now - timedelta(days=1)),
            ("cleanup-never", None),
        ]:
            session.add(Link(code=code, target_url="https://example.com/", expires_at=expires_at))
        session.commit()

        assert purge_expired(session, grace=timedelta(days=7), batch_size=1) == 1
        remaining = set(session.scalars(select(Link.code).where(Link.code.like("cleanup-%"))))
    assert remaining == {"cleanup-recent", "cleanup-never"}
