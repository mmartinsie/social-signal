"""Bluesky clients: an account's own recent posts, and posts with a hashtag.

- Handles: app.bsky.feed.getAuthorFeed on the public AppView, which needs no
  authentication (D5, D18).
- Hashtags: app.bsky.feed.searchPosts (D20). Bluesky blocks unauthenticated
  search at times, to reduce load. With credentials, the ingestor logs in at
  the entryway (bsky.social) and searches through the account's PDS, which
  forwards the request to the AppView. Without them, it searches the AppView
  directly (api.bsky.app), which works while Bluesky allows it.

Every response is untrusted input from the internet: each post is validated,
and one that does not have the expected shape is skipped, never stored.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

AUTHOR_FEED = "/xrpc/app.bsky.feed.getAuthorFeed"
SEARCH_POSTS = "/xrpc/app.bsky.feed.searchPosts"
CREATE_SESSION = "/xrpc/com.atproto.server.createSession"

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
# Maximum page size of both getAuthorFeed and searchPosts.
MAX_LIMIT = 100


class SubscriptionRejected(Exception):
    """Bluesky rejected the subscribed value: an unknown or malformed account,
    or a query it cannot run. A problem with the subscription, not with the
    system."""


class SearchForbidden(Exception):
    """Bluesky answered 403 to a search. Without credentials, this is its
    block on unauthenticated search, which it turns on to reduce load."""


class LoginRejected(Exception):
    """Bluesky rejected the credentials."""


@dataclass(frozen=True)
class Post:
    uri: str
    cid: str
    author_did: str
    author_handle: str
    text: str
    created_at: datetime


@dataclass(frozen=True)
class Credentials:
    identifier: str
    # An app password, never the account's own password (.env.example).
    app_password: str = field(repr=False)


@dataclass(frozen=True)
class Session:
    did: str
    # Where to send requests: the account's own PDS (Bluesky's entryway
    # guide), or the entryway itself if the DID document does not say.
    pds_url: str
    access_jwt: str = field(repr=False)


# The posts to store, and how many were skipped and why.
Fetched = tuple[list[Post], Counter[str]]


def make_client(
    base_url: str, *, access_jwt: str | None = None, timeout: float = 10.0
) -> httpx.Client:
    headers = {"User-Agent": "socialsignal-ingestor"}
    if access_jwt is not None:
        headers["Authorization"] = f"Bearer {access_jwt}"
    return httpx.Client(
        base_url=base_url,
        timeout=timeout,
        headers=headers,
        # Retries only failed connection attempts, never a request that
        # reached Bluesky.
        transport=httpx.HTTPTransport(retries=2),
    )


def create_session(client: httpx.Client, credentials: Credentials) -> Session:
    """Log in at the entryway (the client's base URL).

    Raises LoginRejected when Bluesky rejects the credentials, httpx.HTTPError
    on any other failure (e.g. 429: createSession is limited to 300 per day
    per account), and ValueError when the response is not the expected JSON.
    """
    response = client.post(
        CREATE_SESSION,
        json={"identifier": credentials.identifier, "password": credentials.app_password},
    )
    if response.status_code in (httpx.codes.BAD_REQUEST, httpx.codes.UNAUTHORIZED):
        raise LoginRejected(_error_message(response))
    response.raise_for_status()
    body = response.json()
    try:
        return Session(
            did=_string(body["did"]),
            pds_url=_pds_url(body.get("didDoc")) or str(client.base_url).rstrip("/"),
            access_jwt=_string(body["accessJwt"]),
        )
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("unexpected createSession response") from error


def get_author_posts(
    client: httpx.Client, actor: str, *, limit: int, feed_filter: str
) -> Fetched:
    """The account's latest posts (one page).

    Raises SubscriptionRejected when Bluesky rejects the account,
    httpx.HTTPError on any other HTTP or network failure, and ValueError when
    the response is not the expected JSON.
    """
    response = client.get(
        AUTHOR_FEED, params={"actor": actor, "limit": limit, "filter": feed_filter}
    )
    # limit and filter are validated at start-up, so a 400 can only come
    # from the actor: "Profile not found" or "Invalid AT identifier".
    if response.status_code == httpx.codes.BAD_REQUEST:
        raise SubscriptionRejected(_error_message(response))
    response.raise_for_status()
    return parse_author_feed(response.json())


def search_tag_posts(client: httpx.Client, tag: str, *, limit: int) -> Fetched:
    """The latest posts with the hashtag (one page), without the "#".

    Raises SubscriptionRejected when Bluesky cannot run the query,
    SearchForbidden on 403, httpx.HTTPError on any other failure, and
    ValueError when the response is not the expected JSON.
    """
    response = client.get(
        SEARCH_POSTS,
        # `q` is required; the `tag` filter matches the hashtag facet, so a
        # post that only has the word in its text does not count.
        params={"q": f"#{tag}", "tag": tag, "sort": "latest", "limit": limit},
    )
    if response.status_code == httpx.codes.BAD_REQUEST:
        raise SubscriptionRejected(_error_message(response))
    if response.status_code == httpx.codes.FORBIDDEN:
        raise SearchForbidden(_error_message(response))
    response.raise_for_status()
    return parse_search_posts(response.json())


def parse_author_feed(payload: Any) -> Fetched:
    """Keep the author's own posts that have text; count what is skipped.

    Replies to other accounts are already left out by the feed's filter
    (posts_and_author_threads, D18).
    """
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
            _keep(item["post"], posts, skipped)
        except (KeyError, TypeError, AttributeError, ValueError):
            skipped["invalid"] += 1
    return posts, skipped


def parse_search_posts(payload: Any) -> Fetched:
    """Keep posts with text, except replies to other accounts (D20)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("posts"), list):
        raise ValueError("unexpected searchPosts response: no 'posts' list")
    posts: list[Post] = []
    skipped: Counter[str] = Counter()
    for view in payload["posts"]:
        try:
            if _replies_to_another_account(view):
                skipped["reply to others"] += 1
                continue
            _keep(view, posts, skipped)
        except (KeyError, TypeError, AttributeError, ValueError):
            skipped["invalid"] += 1
    return posts, skipped


def _keep(post_view: dict[str, Any], posts: list[Post], skipped: Counter[str]) -> None:
    post = _parse_post(post_view)
    if post is None:
        skipped["no text"] += 1
    else:
        posts.append(post)


def _replies_to_another_account(post_view: dict[str, Any]) -> bool:
    """The same rule as getAuthorFeed's posts_and_author_threads (D18): a
    reply is kept only if both the post it answers and the thread's first
    post are by the same author. Otherwise it is part of a conversation and
    makes no sense without the other side."""
    reply = post_view["record"].get("reply")
    if reply is None:
        return False
    author = _string(post_view["author"]["did"])
    return any(_uri_did(reply[end]["uri"]) != author for end in ("parent", "root"))


def _uri_did(uri: Any) -> str:
    """The repository (account) of an at:// URI: at://<did>/<collection>/<rkey>."""
    value = _string(uri)
    if not value.startswith("at://"):
        raise ValueError("not an at:// URI")
    return value.removeprefix("at://").split("/", 1)[0]


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


def _pds_url(did_document: Any) -> str | None:
    """The account's PDS from its DID document, if it is an https URL. The
    access token is sent there, so nothing else is accepted."""
    if not isinstance(did_document, dict) or not isinstance(did_document.get("service"), list):
        return None
    for service in did_document["service"]:
        if isinstance(service, dict) and str(service.get("id", "")).endswith("#atproto_pds"):
            endpoint = service.get("serviceEndpoint")
            if isinstance(endpoint, str) and endpoint.startswith("https://"):
                return endpoint
    return None


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
