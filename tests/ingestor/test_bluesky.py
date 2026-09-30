"""Parsing of getAuthorFeed responses and the client's error handling.

The items are synthetic, but follow the shape of real responses from
public.api.bsky.app (checked 2026-09-30): each feed item has a `post` with
uri, cid, author {did, handle}, record {text, createdAt} and indexedAt, and
a repost carries a `reason`.
"""

from datetime import UTC, datetime

import httpx
import pytest

from socialsignal_ingestor import bluesky

AUTHOR_DID = "did:plc:author000000000000000000"


def item(rkey: str = "1", text: str = "Hello", **overrides) -> dict:
    post = {
        "uri": f"at://{AUTHOR_DID}/app.bsky.feed.post/{rkey}",
        "cid": f"bafy{rkey}",
        "author": {"did": AUTHOR_DID, "handle": "author.bsky.social"},
        "record": {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": "2026-09-30T10:00:00.000Z",
        },
        "indexedAt": "2026-09-30T10:00:01.000Z",
    }
    post.update(overrides)
    return {"post": post}


def test_keeps_an_own_post_with_all_its_fields():
    posts, skipped = bluesky.parse_author_feed({"feed": [item()]})

    assert posts == [
        bluesky.Post(
            uri=f"at://{AUTHOR_DID}/app.bsky.feed.post/1",
            cid="bafy1",
            author_did=AUTHOR_DID,
            author_handle="author.bsky.social",
            text="Hello",
            created_at=datetime(2026, 9, 30, 10, 0, 0, tzinfo=UTC),
        )
    ]
    assert not skipped


def test_skips_reposts():
    repost = item() | {"reason": {"$type": "app.bsky.feed.defs#reasonRepost"}}

    posts, skipped = bluesky.parse_author_feed({"feed": [repost, item("2")]})

    assert [p.cid for p in posts] == ["bafy2"]
    assert skipped == {"repost": 1}


@pytest.mark.parametrize("text", ["", "   \n", "\x00"])
def test_skips_posts_without_text(text):
    posts, skipped = bluesky.parse_author_feed({"feed": [item(text=text)]})

    assert posts == []
    assert skipped == {"no text": 1}


def test_removes_nul_characters_from_the_text():
    posts, _ = bluesky.parse_author_feed({"feed": [item(text="a\x00b")]})

    assert posts[0].text == "ab"


def test_a_future_created_at_is_capped_at_indexed_at():
    future = item()
    future["post"]["record"]["createdAt"] = "2030-01-01T00:00:00Z"

    posts, _ = bluesky.parse_author_feed({"feed": [future]})

    assert posts[0].created_at == datetime(2026, 9, 30, 10, 0, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    "broken",
    [
        {"indexedAt": "yesterday"},
        {"indexedAt": "2026-09-30T10:00:01"},  # no time zone
        {"uri": None},
        {"cid": ""},
        {"author": {"did": AUTHOR_DID}},
        {"record": {"text": 42, "createdAt": "2026-09-30T10:00:00Z"}},
    ],
)
def test_skips_malformed_items_without_failing(broken):
    posts, skipped = bluesky.parse_author_feed({"feed": [item(**broken), "junk", item("2")]})

    assert [p.cid for p in posts] == ["bafy2"]
    assert skipped == {"invalid": 2}


@pytest.mark.parametrize("payload", [[], {}, {"feed": None}])
def test_rejects_a_response_without_a_feed(payload):
    with pytest.raises(ValueError):
        bluesky.parse_author_feed(payload)


def client_answering(status: int, body: dict, seen: list | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=body)

    return httpx.Client(base_url="https://bsky.test", transport=httpx.MockTransport(handler))


def test_requests_one_page_of_the_author_feed():
    seen: list[httpx.Request] = []
    client = client_answering(200, {"feed": [item()]}, seen)

    posts, _ = bluesky.get_author_posts(
        client, "author.bsky.social", limit=50, feed_filter="posts_and_author_threads"
    )

    assert len(posts) == 1
    assert seen[0].url.path == "/xrpc/app.bsky.feed.getAuthorFeed"
    assert dict(seen[0].url.params) == {
        "actor": "author.bsky.social",
        "limit": "50",
        "filter": "posts_and_author_threads",
    }


def test_a_rejected_account_raises_actor_error():
    client = client_answering(400, {"error": "InvalidRequest", "message": "Profile not found"})

    with pytest.raises(bluesky.ActorError, match="Profile not found"):
        bluesky.get_author_posts(client, "nobody.test", limit=50, feed_filter="posts_with_replies")


@pytest.mark.parametrize("status", [429, 500, 503])
def test_other_http_errors_raise_http_status_error(status):
    client = client_answering(status, {"error": "Oops"})

    with pytest.raises(httpx.HTTPStatusError):
        bluesky.get_author_posts(client, "author.test", limit=50, feed_filter="posts_with_replies")
