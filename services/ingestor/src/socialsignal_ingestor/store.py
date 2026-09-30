"""Database access of the ingest zone, with the ingestor role's grants only:
SELECT on subscriptions, INSERT on posts and subscription_posts (D1, D16).

Both inserts use ON CONFLICT DO NOTHING *without* a conflict target: naming
one (e.g. `ON CONFLICT (uri)`) needs SELECT on that column, which this role
does not have, so the internet-facing zone cannot find out which posts
exist (D17). The primary key is the only unique constraint on both tables,
so the effect is the same: storing a post again is a no-op (D5).
"""

from collections.abc import Iterable
from dataclasses import dataclass

import psycopg

from socialsignal_ingestor.bluesky import Post

SELECT_HANDLES = "SELECT id, value FROM subscriptions WHERE kind = 'handle' ORDER BY id"

INSERT_POST = """
    INSERT INTO posts (uri, cid, author_did, author_handle, text, created_at)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT DO NOTHING
"""

INSERT_LINK = """
    INSERT INTO subscription_posts (subscription_id, post_uri)
    VALUES (%s, %s)
    ON CONFLICT DO NOTHING
"""


@dataclass(frozen=True)
class Subscription:
    id: int
    value: str


@dataclass(frozen=True)
class StoreResult:
    new_posts: int
    new_links: int


def handle_subscriptions(connection: psycopg.Connection) -> list[Subscription]:
    rows = connection.execute(SELECT_HANDLES).fetchall()
    return [Subscription(id=row[0], value=row[1]) for row in rows]


def store_posts(
    connection: psycopg.Connection, subscription_id: int, posts: Iterable[Post]
) -> StoreResult:
    """Store the posts and link them to the subscription, all or nothing.

    rowcount tells new rows (1) from existing ones (0) without reading the
    table. Raises psycopg.errors.ForeignKeyViolation if the subscription was
    deleted meanwhile; nothing is stored then.
    """
    new_posts = new_links = 0
    with connection.transaction(), connection.cursor() as cursor:
        for post in posts:
            cursor.execute(
                INSERT_POST,
                (
                    post.uri,
                    post.cid,
                    post.author_did,
                    post.author_handle,
                    post.text,
                    post.created_at,
                ),
            )
            new_posts += cursor.rowcount
            cursor.execute(INSERT_LINK, (subscription_id, post.uri))
            new_links += cursor.rowcount
    return StoreResult(new_posts=new_posts, new_links=new_links)
