"""Database access of the API, with the analysis role's grants only (D1,
D16): it manages subscriptions and reads the summaries the worker
precomputed (A3). It never calls the LLM.

One connection per request (D25): the traffic of an analysts' UI is small,
and a request never depends on a connection that broke while PostgreSQL
restarted.
"""

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

import psycopg

# Each subscription with its summary, if the worker wrote one, and whether
# the ingestor ever stored a post for it: a subscription Bluesky does not
# know, or one not fetched yet, has none.
SELECT_SUBSCRIPTIONS = """
    SELECT s.id, s.kind, s.value, s.created_at,
           EXISTS (SELECT 1 FROM subscription_posts AS sp WHERE sp.subscription_id = s.id),
           m.dominant_label, m.positive_count, m.neutral_count, m.negative_count,
           m.item_count, m.summary_text, m.updated_at
    FROM subscriptions AS s
    LEFT JOIN summaries AS m ON m.subscription_id = s.id
    ORDER BY s.kind, s.value
"""

# Subscribing twice is not an error: the existing subscription is kept.
INSERT_SUBSCRIPTION = """
    INSERT INTO subscriptions (kind, value) VALUES (%s, %s)
    ON CONFLICT (kind, value) DO NOTHING
    RETURNING id
"""

SELECT_SUBSCRIPTION_ID = "SELECT id FROM subscriptions WHERE kind = %s AND value = %s"

# The foreign keys cascade: its links and its summary go with it. Its posts
# and their labels stay, so subscribing again is quick.
DELETE_SUBSCRIPTION = "DELETE FROM subscriptions WHERE id = %s"


@dataclass(frozen=True)
class Summary:
    dominant_label: str | None
    positive: int
    neutral: int
    negative: int
    item_count: int
    # None when the LLM could not write it (degraded mode, A3).
    text: str | None
    updated_at: datetime


@dataclass(frozen=True)
class Subscription:
    id: int
    kind: str
    value: str
    created_at: datetime
    has_posts: bool
    summary: Summary | None


class Unavailable(Exception):
    """The database cannot be reached: the page says so, with a 503."""


class Store:
    def __init__(self, connect: Callable[[], psycopg.Connection]):
        self._connect = connect

    @contextmanager
    def _connection(self):
        # Connecting, or a connection lost halfway: both mean unavailable.
        try:
            with self._connect() as connection:
                yield connection
        except psycopg.OperationalError as error:
            raise Unavailable(str(error)) from error

    def subscriptions(self) -> list[Subscription]:
        with self._connection() as connection:
            rows = connection.execute(SELECT_SUBSCRIPTIONS).fetchall()
        return [_subscription(row) for row in rows]

    def subscribe(self, kind: str, value: str) -> tuple[int, bool]:
        """The subscription's id, and whether it was created now."""
        with self._connection() as connection:
            row = connection.execute(INSERT_SUBSCRIPTION, (kind, value)).fetchone()
            if row is not None:
                return row[0], True
            row = connection.execute(SELECT_SUBSCRIPTION_ID, (kind, value)).fetchone()
        return row[0], False

    def unsubscribe(self, subscription_id: int) -> bool:
        """False if there was no such subscription."""
        with self._connection() as connection:
            return connection.execute(DELETE_SUBSCRIPTION, (subscription_id,)).rowcount > 0


def _subscription(row) -> Subscription:
    id_, kind, value, created_at, has_posts, label, pos, neu, neg, items, text, updated = row
    summary = None
    if updated is not None:
        summary = Summary(label, pos, neu, neg, items, text, updated)
    return Subscription(id_, kind, value, created_at, has_posts, summary)
