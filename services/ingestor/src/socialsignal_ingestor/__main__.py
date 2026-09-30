"""Entry point of the ingestor CronJobs:

    python -m socialsignal_ingestor handles
    python -m socialsignal_ingestor hashtags

One run reads the latest posts of every subscription of that kind and
stores them. Each subscription is stored in its own transaction, so one
failure never blocks the others. Handles and hashtags run as separate
CronJobs (D20): only the hashtag one holds the Bluesky credentials, and it
runs less often, because logging in is rate limited.

Exit status:
  0  every subscription was stored or skipped for a known reason: Bluesky
     rejected the subscribed value, or it is blocking unauthenticated
     search and there are no credentials (both logged as warnings).
  1  a network, Bluesky or database error prevented storing at least one
     subscription, or the credentials were rejected, so the failed Job is
     visible in `kubectl get jobs`.
"""

import argparse
import logging
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import httpx
import psycopg

from socialsignal_common.db import DatabaseSettings, connect
from socialsignal_ingestor import bluesky, store

log = logging.getLogger("socialsignal_ingestor")


@dataclass(frozen=True)
class IngestorSettings:
    # Handles: the public, cached AppView (D5).
    public_api_url: str
    # Hashtags without credentials: the AppView itself, since the public one
    # always blocks search (D20).
    search_api_url: str
    # Hashtags with credentials: where to log in (D20).
    entryway_url: str
    # One page per subscription and run. The worker summarises the last 50
    # posts of the last 7 days (A2), so one page of 50 is enough.
    posts_per_handle: int
    posts_per_hashtag: int
    # posts_and_author_threads: the account's posts and its own threads, but
    # not its replies to other accounts, which make no sense without the
    # post they answer and are often sarcastic (author's decision, D18).
    author_feed_filter: str
    # Optional app password for hashtag search, mounted from a Secret (D20).
    credentials: bluesky.Credentials | None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> "IngestorSettings":
        settings = cls(
            public_api_url=environ.get("BLUESKY_PUBLIC_API_URL", "https://public.api.bsky.app"),
            search_api_url=environ.get("BLUESKY_SEARCH_API_URL", "https://api.bsky.app"),
            entryway_url=environ.get("BLUESKY_ENTRYWAY_URL", "https://bsky.social"),
            posts_per_handle=int(environ.get("INGEST_POSTS_PER_HANDLE", "50")),
            posts_per_hashtag=int(environ.get("INGEST_POSTS_PER_HASHTAG", "50")),
            author_feed_filter=environ.get("INGEST_AUTHOR_FEED_FILTER", "posts_and_author_threads"),
            credentials=load_credentials(
                Path(environ.get("BLUESKY_CREDENTIALS_DIR", "/run/secrets/bluesky"))
            ),
        )
        # Bluesky answers 400 to a bad limit and silently ignores an unknown
        # filter: fail here instead, so a 400 always means a bad subscription.
        for name, value in (
            ("INGEST_POSTS_PER_HANDLE", settings.posts_per_handle),
            ("INGEST_POSTS_PER_HASHTAG", settings.posts_per_hashtag),
        ):
            if not 1 <= value <= bluesky.MAX_LIMIT:
                raise ValueError(f"{name} must be 1-{bluesky.MAX_LIMIT}")
        if settings.author_feed_filter not in bluesky.AUTHOR_FEED_FILTERS:
            raise ValueError(
                f"INGEST_AUTHOR_FEED_FILTER must be one of {sorted(bluesky.AUTHOR_FEED_FILTERS)}"
            )
        return settings


def load_credentials(directory: Path) -> bluesky.Credentials | None:
    """Read `identifier` and `app-password` from the mounted Secret.

    None when there are no credentials: the Secret is optional, and without
    it the volume is an empty directory. Only one of the two is an error.
    """
    values = {}
    for name in ("identifier", "app-password"):
        path = directory / name
        values[name] = path.read_text().strip() if path.is_file() else ""
    if not any(values.values()):
        return None
    if not all(values.values()):
        raise ValueError(f"{directory} needs both 'identifier' and 'app-password'")
    return bluesky.Credentials(identifier=values["identifier"], app_password=values["app-password"])


def store_fetched(
    connection: psycopg.Connection,
    subscription: store.Subscription,
    name: str,
    fetched: bluesky.Fetched,
) -> bool:
    """Store one subscription's posts. False if it failed."""
    posts, skipped = fetched
    try:
        result = store.store_posts(connection, subscription.id, posts)
    except psycopg.errors.ForeignKeyViolation:
        log.info("%s: unsubscribed during the run, nothing stored", name)
        return True
    except psycopg.Error as error:
        log.error("%s: could not store posts: %s", name, error)
        return False
    log.info(
        "%s: %d posts kept, skipped %s; %d new posts, %d new links",
        name,
        len(posts),
        dict(skipped) or "none",
        result.new_posts,
        result.new_links,
    )
    return True


def run_handles(connection: psycopg.Connection, settings: IngestorSettings) -> int:
    """Ingest every handle subscription. Returns how many failed."""
    subscriptions = store.subscriptions(connection, "handle")
    log.info("%d handle subscriptions", len(subscriptions))
    failed = 0
    with bluesky.make_client(settings.public_api_url) as client:
        for subscription in subscriptions:
            name = f"@{subscription.value}"
            try:
                fetched = bluesky.get_author_posts(
                    client,
                    subscription.value,
                    limit=settings.posts_per_handle,
                    feed_filter=settings.author_feed_filter,
                )
            except bluesky.SubscriptionRejected as error:
                log.warning("%s: skipped, Bluesky rejected the account (%s)", name, error)
                continue
            except (httpx.HTTPError, ValueError) as error:
                log.error("%s: could not read the feed: %s", name, error)
                failed += 1
                continue
            failed += not store_fetched(connection, subscription, name, fetched)
    return failed


def run_hashtags(connection: psycopg.Connection, settings: IngestorSettings) -> int:
    """Ingest every hashtag subscription. Returns how many failed."""
    subscriptions = store.subscriptions(connection, "hashtag")
    log.info("%d hashtag subscriptions", len(subscriptions))
    if not subscriptions:
        # Nothing to search: do not spend one of the day's logins.
        return 0

    if settings.credentials is None:
        log.info("no Bluesky credentials: searching without authentication")
        base_url, access_jwt = settings.search_api_url, None
    else:
        try:
            with bluesky.make_client(settings.entryway_url) as client:
                session = bluesky.create_session(client, settings.credentials)
        except (bluesky.LoginRejected, httpx.HTTPError, ValueError) as error:
            log.error(
                "could not log in to Bluesky as %s: %s", settings.credentials.identifier, error
            )
            return len(subscriptions)
        log.info("logged in to Bluesky as %s; searching through %s", session.did, session.pds_url)
        base_url, access_jwt = session.pds_url, session.access_jwt

    failed = 0
    with bluesky.make_client(base_url, access_jwt=access_jwt) as client:
        for subscription in subscriptions:
            name = f"#{subscription.value}"
            try:
                fetched = bluesky.search_tag_posts(
                    client, subscription.value, limit=settings.posts_per_hashtag
                )
            except bluesky.SubscriptionRejected as error:
                log.warning("%s: skipped, Bluesky rejected the search (%s)", name, error)
                continue
            except bluesky.SearchForbidden as error:
                if access_jwt is None:
                    # A known, external state, not a failure of this system:
                    # stop here instead of repeating the same request.
                    log.warning(
                        "Bluesky is blocking unauthenticated search (%s): %d hashtag "
                        "subscriptions not updated. Add credentials to .env and run "
                        "`make start` (see .env.example).",
                        error,
                        len(subscriptions),
                    )
                    return failed
                log.error("%s: search forbidden with credentials: %s", name, error)
                failed += 1
                continue
            except (httpx.HTTPError, ValueError) as error:
                log.error("%s: could not search: %s", name, error)
                failed += 1
                continue
            failed += not store_fetched(connection, subscription, name, fetched)
    return failed


RUNS = {"handles": run_handles, "hashtags": run_hashtags}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m socialsignal_ingestor",
        description="Read the latest Bluesky posts of every subscription of one kind.",
    )
    parser.add_argument("kind", choices=sorted(RUNS))
    kind = parser.parse_args(argv).kind

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # httpx logs every request at INFO; our own lines already say enough.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = IngestorSettings.from_env()
    database = DatabaseSettings.from_env()

    with connect(database, application_name=f"socialsignal-ingestor-{kind}") as connection:
        failed = RUNS[kind](connection, settings)

    if failed:
        log.error("%d %s subscriptions failed", failed, kind.removesuffix("s"))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
