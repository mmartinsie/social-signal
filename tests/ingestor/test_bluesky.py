"""Parsing of getAuthorFeed and searchPosts responses, login, and the
client's error handling.

The items are synthetic, but follow the shape of real responses (checked
2026-09-30): a post has uri, cid, author {did, handle}, record {text,
createdAt, reply?} and indexedAt; a feed item wraps it in `post`, and a
repost carries a `reason`; searchPosts returns posts directly.
"""

import json
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


def test_a_rejected_account_raises_subscription_rejected():
    client = client_answering(400, {"error": "InvalidRequest", "message": "Profile not found"})

    with pytest.raises(bluesky.SubscriptionRejected, match="Profile not found"):
        bluesky.get_author_posts(client, "nobody.test", limit=50, feed_filter="posts_with_replies")


@pytest.mark.parametrize("status", [429, 500, 503])
def test_other_http_errors_raise_http_status_error(status):
    client = client_answering(status, {"error": "Oops"})

    with pytest.raises(httpx.HTTPStatusError):
        bluesky.get_author_posts(client, "author.test", limit=50, feed_filter="posts_with_replies")


# ---------------------------------------------------------------- search ---

OTHER_DID = "did:plc:other0000000000000000000"


def post_uri(did: str, rkey: str = "p") -> str:
    return f"at://{did}/app.bsky.feed.post/{rkey}"


def reply(rkey: str, parent_did: str, root_did: str) -> dict:
    view = item(rkey)["post"]
    view["record"]["reply"] = {
        "parent": {"uri": post_uri(parent_did), "cid": "bafyparent"},
        "root": {"uri": post_uri(root_did), "cid": "bafyroot"},
    }
    return view


def test_search_keeps_posts_and_own_threads_but_not_replies_to_others():
    views = [
        item("1")["post"],
        reply("2", parent_did=AUTHOR_DID, root_did=AUTHOR_DID),  # own thread
        reply("3", parent_did=OTHER_DID, root_did=OTHER_DID),  # answers someone
        reply("4", parent_did=AUTHOR_DID, root_did=OTHER_DID),  # in someone's thread
    ]

    posts, skipped = bluesky.parse_search_posts({"posts": views})

    assert [p.cid for p in posts] == ["bafy1", "bafy2"]
    assert skipped == {"reply to others": 2}


def test_search_skips_a_reply_with_a_malformed_parent():
    broken = reply("1", parent_did=AUTHOR_DID, root_did=AUTHOR_DID)
    broken["record"]["reply"]["parent"]["uri"] = "https://example.com/not-at-uri"

    posts, skipped = bluesky.parse_search_posts({"posts": [broken, item("2")["post"]]})

    assert [p.cid for p in posts] == ["bafy2"]
    assert skipped == {"invalid": 1}


@pytest.mark.parametrize("payload", [[], {}, {"posts": None}, {"feed": []}])
def test_rejects_a_search_response_without_posts(payload):
    with pytest.raises(ValueError):
        bluesky.parse_search_posts(payload)


def test_searches_the_latest_posts_with_the_hashtag_facet():
    seen: list[httpx.Request] = []
    client = client_answering(200, {"posts": [item()["post"]]}, seen)

    posts, _ = bluesky.search_tag_posts(client, "python", limit=50)

    assert len(posts) == 1
    assert seen[0].url.path == "/xrpc/app.bsky.feed.searchPosts"
    assert dict(seen[0].url.params) == {
        "q": "#python",
        "tag": "python",
        "sort": "latest",
        "limit": "50",
    }


def test_a_rejected_query_raises_subscription_rejected():
    client = client_answering(400, {"error": "BadQueryString", "message": "bad"})

    with pytest.raises(bluesky.SubscriptionRejected, match="BadQueryString"):
        bluesky.search_tag_posts(client, "python", limit=50)


def test_a_blocked_search_raises_search_forbidden():
    # Bluesky's block answers with an HTML page, not JSON.
    client = httpx.Client(
        base_url="https://bsky.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(403, text="<html>403</html>")),
    )

    with pytest.raises(bluesky.SearchForbidden, match="HTTP 403"):
        bluesky.search_tag_posts(client, "python", limit=50)


# ----------------------------------------------------------------- login ---

CREDENTIALS = bluesky.Credentials(identifier="me.bsky.social", app_password="abcd-efgh-ijkl-mnop")


def session_body(pds: str | None = "https://morel.us-east.host.bsky.network") -> dict:
    body = {"did": AUTHOR_DID, "handle": "me.bsky.social", "accessJwt": "access", "refreshJwt": "r"}
    if pds is not None:
        body["didDoc"] = {
            "id": AUTHOR_DID,
            "service": [
                {
                    "id": "#atproto_pds",
                    "type": "AtprotoPersonalDataServer",
                    "serviceEndpoint": pds,
                }
            ],
        }
    return body


def test_login_posts_the_credentials_and_uses_the_account_pds():
    seen: list[httpx.Request] = []
    client = client_answering(200, session_body(), seen)

    session = bluesky.create_session(client, CREDENTIALS)

    assert seen[0].method == "POST"
    assert seen[0].url.path == "/xrpc/com.atproto.server.createSession"
    assert json.loads(seen[0].content) == {
        "identifier": "me.bsky.social",
        "password": "abcd-efgh-ijkl-mnop",
    }
    assert session == bluesky.Session(
        did=AUTHOR_DID,
        pds_url="https://morel.us-east.host.bsky.network",
        access_jwt="access",
    )


@pytest.mark.parametrize("pds", [None, "http://plain-http.example"])
def test_login_falls_back_to_the_entryway_without_an_https_pds(pds):
    client = client_answering(200, session_body(pds))

    session = bluesky.create_session(client, CREDENTIALS)

    assert session.pds_url == "https://bsky.test"


@pytest.mark.parametrize("status", [400, 401])
def test_rejected_credentials_raise_login_rejected(status):
    body = {"error": "AuthenticationRequired", "message": "Invalid identifier or password"}
    client = client_answering(status, body)

    with pytest.raises(bluesky.LoginRejected, match="Invalid identifier or password"):
        bluesky.create_session(client, CREDENTIALS)


def test_secrets_never_appear_in_repr():
    session = bluesky.Session(did=AUTHOR_DID, pds_url="https://pds.test", access_jwt="access")

    assert "abcd-efgh-ijkl-mnop" not in repr(CREDENTIALS)
    assert "access" not in repr(session)


def test_an_authenticated_client_sends_the_bearer_token():
    with bluesky.make_client("https://pds.test", access_jwt="access") as client:
        assert client.headers["Authorization"] == "Bearer access"
    with bluesky.make_client("https://pds.test") as client:
        assert "Authorization" not in client.headers
