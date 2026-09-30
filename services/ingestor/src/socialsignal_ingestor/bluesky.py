"""Client for Bluesky's public AppView: an account's own recent posts.

Uses app.bsky.feed.getAuthorFeed, which needs no authentication (D5). The
response is untrusted input from the internet: every item is validated, and
an item that does not have the expected shape is skipped, never stored.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

AUTHOR_FEED = "/xrpc/app.bsky.feed.getAuthorFeed"

# Values of getAuthorFeed's `filter` parameter (its lexicon). Bluesky ignores
# an unknown value and falls back to posts_with_replies, so a typo would
# silently change what we store: settings are checked against this list.
AUTHOR_FEED_FILTERS = frozenset(
    {
        "posts_with_replies",
        "posts_no_replies",
        "posts_with_media",
        "posts_and_author_threads",
        "posts_with_video",
    }
)
MAX_LIMIT = 100


class ActorError(Exception):
    """Bluesky rejected the subscribed account: unknown, or not a valid
    handle or DID. A problem with the subscription, not with the system."""


@dataclass(frozen=True)
class Post:
    uri: str
    cid: str
    author_did: str
    author_handle: str
    text: str
    created_at: datetime


def make_client(base_url: str, timeout: float = 10.0) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        timeout=timeout,
        headers={"User-Agent": "socialsignal-ingestor"},
        # Retries only failed connection attempts, never a request that
        # reached Bluesky.
        transport=httpx.HTTPTransport(retries=2),
    )


def get_author_posts(
    client: httpx.Client, actor: str, *, limit: int, feed_filter: str
) -> tuple[list[Post], Counter[str]]:
    """The account's latest posts (one page) and why any items were skipped.

    Raises ActorError when Bluesky rejects the account, httpx.HTTPError on
    any other HTTP or network failure, and ValueError when the response is
    not the expected JSON.
    """
    response = client.get(
        AUTHOR_FEED, params={"actor": actor, "limit": limit, "filter": feed_filter}
    )
    # limit and filter are validated at start-up, so a 400 can only come
    # from the actor: "Profile not found" or "Invalid AT identifier".
    if response.status_code == httpx.codes.BAD_REQUEST:
        raise ActorError(_error_message(response))
    response.raise_for_status()
    return parse_author_feed(response.json())


def parse_author_feed(payload: Any) -> tuple[list[Post], Counter[str]]:
    """Keep the author's own posts that have text; count what is skipped."""
    if not isinstance(payload, dict) or not isinstance(payload.get("feed"), list):
        raise ValueError("unexpected getAuthorFeed response: no 'feed' list")
    posts: list[Post] = []
    skipped: Counter[str] = Counter()
    for item in payload["feed"]:
        try:
            if item.get("reason") is not None:
                # A repost: someone else's words (reasonRepost). Also any
                # other reason Bluesky may add, e.g. a pinned post.
                skipped["repost"] += 1
                continue
            post = _parse_post(item["post"])
        except (KeyError, TypeError, AttributeError, ValueError):
            skipped["invalid"] += 1
            continue
        if post is None:
            skipped["no text"] += 1
        else:
            posts.append(post)
    return posts, skipped


def _parse_post(post: dict[str, Any]) -> Post | None:
    record = post["record"]
    text = record["text"]
    if not isinstance(text, str):
        raise ValueError("post text is not a string")
    # PostgreSQL text cannot hold NUL characters, which JSON allows.
    text = text.replace("\x00", "")
    if not text.strip():
        # Only an image or a link: nothing to classify.
        return None
    # createdAt is set by the author's client and can be in the future;
    # indexedAt is when Bluesky received the post. Never later than that, so
    # a future date cannot keep a post among the "most recent" forever.
    created_at = min(_timestamp(record["createdAt"]), _timestamp(post["indexedAt"]))
    return Post(
        uri=_string(post["uri"]),
        cid=_string(post["cid"]),
        author_did=_string(post["author"]["did"]),
        author_handle=_string(post["author"]["handle"]),
        text=text,
        created_at=created_at,
    )


def _string(value: Any) -> str:
    """A non-empty string that PostgreSQL can store (no NUL characters)."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("expected a non-empty string without NUL characters")
    return value


def _timestamp(value: Any) -> datetime:
    parsed = datetime.fromisoformat(_string(value))
    if parsed.tzinfo is None:
        # AT Protocol datetimes always carry a time zone.
        raise ValueError("timestamp without a time zone")
    return parsed


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        return f"{body['error']}: {body['message']}"
    except (ValueError, KeyError, TypeError):
        return f"HTTP {response.status_code}"
