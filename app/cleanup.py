"""Delete links that expired more than a grace period ago.

Run with:  python -m app.cleanup [--grace-days N]

During the grace period an expired link still answers 410 Gone (and its stats stay
visible); after it, the link is deleted and its code becomes free again.
"""

import argparse
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import Link

DEFAULT_GRACE_DAYS = 7
BATCH_SIZE = 1000

log = logging.getLogger("shrinkr.cleanup")


def purge_expired(session: Session, grace: timedelta, batch_size: int = BATCH_SIZE) -> int:
    """Delete links whose expiry is older than `grace`. Returns how many were deleted."""
    cutoff = datetime.now(UTC) - grace
    total = 0
    while True:
        # Small batches, each in its own transaction, keep row locks short so redirects
        # aren't blocked by one huge DELETE.
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
    parser.add_argument(
        "--grace-days",
        type=int,
        default=DEFAULT_GRACE_DAYS,
        help=f"keep expired links this many days before deleting (default: {DEFAULT_GRACE_DAYS})",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    with SessionLocal() as session:
        deleted = purge_expired(session, timedelta(days=args.grace_days))
    log.info("Deleted %d expired link(s) (grace period: %d days)", deleted, args.grace_days)


if __name__ == "__main__":
    main()
