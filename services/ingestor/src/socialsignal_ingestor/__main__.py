"""Entry point of the ingestor CronJob: `python -m socialsignal_ingestor`.

One run: for every handle subscription, fetch the account's latest posts and
store them. Each subscription is stored in its own transaction, so one
failure never blocks the others.

Exit status:
  0  every subscription was stored, or skipped because Bluesky rejected the
     account (a problem with the subscription, reported as a warning; it
     would otherwise fail every run until someone unsubscribes).
  1  a network, Bluesky or database error prevented storing at least one
     subscription, so the failed Job is visible in `kubectl get jobs`.
"""

import logging
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass

import httpx
import psycopg

from socialsignal_common.db import DatabaseSettings, connect
from socialsignal_ingestor import bluesky, store

log = logging.getLogger("socialsignal_ingestor")


@dataclass(frozen=True)
class IngestorSettings:
    bluesky_url: str
    # One page per handle and run. The worker summarises the last 50 posts
    # of the last 7 days (A2), so one page of 50 is enough.
    posts_per_handle: int
    # posts_and_author_threads: the account's posts and its own threads, but
    # not its replies to other accounts, which make no sense without the
    # post they answer and are often sarcastic (author's decision, D18).
    author_feed_filter: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> "IngestorSettings":
        settings = cls(
            bluesky_url=environ.get("BLUESKY_PUBLIC_API_URL", "https://public.api.bsky.app"),
            posts_per_handle=int(environ.get("INGEST_POSTS_PER_HANDLE", "50")),
            author_feed_filter=environ.get("INGEST_AUTHOR_FEED_FILTER", "posts_and_author_threads"),
        )
        # Bluesky answers 400 to a bad limit and silently ignores an unknown
        # filter: fail here instead, so a 400 always means a bad subscription.
        if not 1 <= settings.posts_per_handle <= bluesky.MAX_LIMIT:
            raise ValueError(f"INGEST_POSTS_PER_HANDLE must be 1-{bluesky.MAX_LIMIT}")
        if settings.author_feed_filter not in bluesky.AUTHOR_FEED_FILTERS:
            raise ValueError(
                f"INGEST_AUTHOR_FEED_FILTER must be one of {sorted(bluesky.AUTHOR_FEED_FILTERS)}"
            )
        return settings


def ingest_handle(
    connection: psycopg.Connection,
    client: httpx.Client,
    settings: IngestorSettings,
    subscription: store.Subscription,
) -> bool:
    """Fetch and store one handle's posts. False if it failed."""
    handle = subscription.value
    try:
        posts, skipped = bluesky.get_author_posts(
            client,
            handle,
            limit=settings.posts_per_handle,
            feed_filter=settings.author_feed_filter,
        )
    except bluesky.ActorError as error:
        log.warning("@%s: skipped, Bluesky rejected the account (%s)", handle, error)
        return True
    except (httpx.HTTPError, ValueError) as error:
        log.error("@%s: could not read the feed: %s", handle, error)
        return False

    try:
        result = store.store_posts(connection, subscription.id, posts)
    except psycopg.errors.ForeignKeyViolation:
        log.info("@%s: unsubscribed during the run, nothing stored", handle)
        return True
    except psycopg.Error as error:
        log.error("@%s: could not store posts: %s", handle, error)
        return False

    log.info(
        "@%s: %d posts kept, skipped %s; %d new posts, %d new links",
        handle,
        len(posts),
        dict(skipped) or "none",
        result.new_posts,
        result.new_links,
    )
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # httpx logs every request at INFO; our own lines already say enough.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = IngestorSettings.from_env()
    database = DatabaseSettings.from_env()

    with (
        connect(database, application_name="socialsignal-ingestor") as connection,
        bluesky.make_client(settings.bluesky_url) as client,
    ):
        subscriptions = store.handle_subscriptions(connection)
        log.info("%d handle subscriptions", len(subscriptions))
        failed = sum(
            not ingest_handle(connection, client, settings, subscription)
            for subscription in subscriptions
        )

    if failed:
        log.error("%d of %d subscriptions failed", failed, len(subscriptions))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
