"""Delete links that expired more than --grace-days ago (default 7).

Usage: python -m app.cleanup [--grace-days N]
"""

import argparse
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import Link

BATCH_SIZE = 1000

log = logging.getLogger("shrinkr.cleanup")


def purge_expired(session: Session, grace: timedelta, batch_size: int = BATCH_SIZE) -> int:
    cutoff = datetime.now(UTC) - grace
    total = 0
    while True:
        # Small batches keep each transaction (and its row locks) short.
        batch = select(Link.id).where(Link.expires_at < cutoff).limit(batch_size)
        result = session.execute(
            delete(Link).where(Link.id.in_(batch)).execution_options(synchronize_session=False)
        )
        session.commit()
        total += result.rowcount
        if result.rowcount < batch_size:
            return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete links that expired long ago.")
    parser.add_argument("--grace-days", type=int, default=7)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with SessionLocal() as session:
        deleted = purge_expired(session, timedelta(days=args.grace_days))
    log.info("Deleted %d expired link(s)", deleted)


if __name__ == "__main__":
    main()
