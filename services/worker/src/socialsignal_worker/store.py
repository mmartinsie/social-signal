"""Database access of the worker, with the analysis role's grants only
(D1, D16): it reads subscriptions, posts and their links, stores each post's
label once (A9) and writes one summary per subscription (A3).
"""

from dataclasses import dataclass
from datetime import datetime

import psycopg

from socialsignal_worker.summary import Counts

# The subscription whose summary is oldest goes first, and one without a
# summary before any other: a run cut short by its time budget never starves
# the same subscriptions twice.
SELECT_SUBSCRIPTIONS = """
    SELECT s.id, s.kind, s.value
    FROM subscriptions AS s
    LEFT JOIN summaries AS m ON m.subscription_id = s.id
    ORDER BY m.updated_at NULLS FIRST, s.id
"""

# "Recent" (A2): the subscription's latest posts within the window, newest
# first, each with its label if it has one.
SELECT_WINDOW = """
    SELECT p.uri, p.text, ps.label, ps.classified_at
    FROM subscription_posts AS sp
    JOIN posts AS p ON p.uri = sp.post_uri
    LEFT JOIN post_sentiments AS ps ON ps.post_uri = p.uri
    WHERE sp.subscription_id = %(subscription_id)s
      AND p.created_at > now() - make_interval(days => %(days)s::int)
    ORDER BY p.created_at DESC, p.uri
    LIMIT %(limit)s
"""

# A post shared by two subscriptions is classified once. The conflict target
# needs SELECT on post_sentiments, which this role has.
INSERT_LABEL = """
    INSERT INTO post_sentiments (post_uri, label, model)
    VALUES (%s, %s, %s)
    ON CONFLICT (post_uri) DO NOTHING
"""

SELECT_SUMMARY = """
    SELECT positive_count, neutral_count, negative_count, summary_text, updated_at
    FROM summaries
    WHERE subscription_id = %s
"""

# updated_at is the database's clock, like classified_at, so the two can be
# compared (see Summary).
UPSERT_SUMMARY = """
    INSERT INTO summaries (
        subscription_id, dominant_label, positive_count, neutral_count,
        negative_count, item_count, summary_text, updated_at
    )
    VALUES (
        %(subscription_id)s, %(dominant_label)s, %(positive)s, %(neutral)s,
        %(negative)s, %(total)s, %(summary_text)s, now()
    )
    ON CONFLICT (subscription_id) DO UPDATE SET
        dominant_label = EXCLUDED.dominant_label,
        positive_count = EXCLUDED.positive_count,
        neutral_count = EXCLUDED.neutral_count,
        negative_count = EXCLUDED.negative_count,
        item_count = EXCLUDED.item_count,
        summary_text = EXCLUDED.summary_text,
        updated_at = EXCLUDED.updated_at
"""


@dataclass(frozen=True)
class Subscription:
    id: int
    kind: str
    # Normalised by the API: a handle without "@", a hashtag without "#".
    value: str

    @property
    def name(self) -> str:
        return f"@{self.value}" if self.kind == "handle" else f"#{self.value}"


@dataclass(frozen=True)
class WindowPost:
    uri: str
    text: str
    label: str | None
    classified_at: datetime | None


@dataclass(frozen=True)
class Summary:
    counts: Counts
    summary_text: str | None
    # When the summary was last generated: it only changes when its posts
    # change or its sentence is written (author's decision, D24).
    updated_at: datetime


def subscriptions(connection: psycopg.Connection) -> list[Subscription]:
    rows = connection.execute(SELECT_SUBSCRIPTIONS).fetchall()
    return [Subscription(id=row[0], kind=row[1], value=row[2]) for row in rows]


def window(
    connection: psycopg.Connection, subscription_id: int, limit: int, days: int
) -> list[WindowPost]:
    rows = connection.execute(
        SELECT_WINDOW, {"subscription_id": subscription_id, "days": days, "limit": limit}
    ).fetchall()
    return [WindowPost(*row) for row in rows]


def save_label(connection: psycopg.Connection, post_uri: str, label: str, model: str) -> None:
    connection.execute(INSERT_LABEL, (post_uri, label, model))


def current_summary(connection: psycopg.Connection, subscription_id: int) -> Summary | None:
    row = connection.execute(SELECT_SUMMARY, (subscription_id,)).fetchone()
    if row is None:
        return None
    positive, neutral, negative, summary_text, updated_at = row
    return Summary(Counts(positive, neutral, negative), summary_text, updated_at)


def write_summary(
    connection: psycopg.Connection,
    subscription_id: int,
    counts: Counts,
    dominant_label: str | None,
    summary_text: str | None,
) -> None:
    """Insert or replace the subscription's summary, with updated_at = now.

    Raises psycopg.errors.ForeignKeyViolation if the subscription was
    deleted meanwhile; nothing is stored then.
    """
    connection.execute(
        UPSERT_SUMMARY,
        {
            "subscription_id": subscription_id,
            "dominant_label": dominant_label,
            **counts.as_dict(),
            "total": counts.total,
            "summary_text": summary_text,
        },
    )
