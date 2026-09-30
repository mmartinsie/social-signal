"""The hybrid hashtag run (D20): with credentials it logs in and searches
through the account's PDS; without them it searches the AppView directly,
and Bluesky's block on unauthenticated search is a warning, not a failure.

The database is replaced by fakes of store.subscriptions/store_posts, and
Bluesky by an httpx.MockTransport that records every request.
"""

import httpx
import pytest

from socialsignal_ingestor import __main__ as ingestor
from socialsignal_ingestor import bluesky, store

PDS = "https://morel.us-east.host.bsky.network"
SUBSCRIPTIONS = [store.Subscription(id=1, value="python"), store.Subscription(id=2, value="rust")]
POST = {
    "uri": "at://did:plc:a/app.bsky.feed.post/1",
    "cid": "bafy1",
    "author": {"did": "did:plc:a", "handle": "a.bsky.social"},
    "record": {"text": "#python is nice", "createdAt": "2026-09-30T10:00:00Z"},
    "indexedAt": "2026-09-30T10:00:01Z",
}


def settings(credentials: bluesky.Credentials | None) -> ingestor.IngestorSettings:
    return ingestor.IngestorSettings(
        public_api_url="https://public.api.test",
        search_api_url="https://api.test",
        entryway_url="https://entryway.test",
        posts_per_handle=50,
        posts_per_hashtag=50,
        author_feed_filter="posts_and_author_threads",
        credentials=credentials,
    )


class FakeBluesky:
    """Answers createSession and searchPosts; records what was asked."""

    def __init__(self, login_status: int = 200, search_status: int = 200):
        self.login_status = login_status
        self.search_status = search_status
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("createSession"):
            if self.login_status != 200:
                error = {"error": "AuthenticationRequired", "message": "no"}
                return httpx.Response(self.login_status, json=error)
            did_doc = {"service": [{"id": "#atproto_pds", "serviceEndpoint": PDS}]}
            session = {"did": "did:plc:me", "accessJwt": "access", "didDoc": did_doc}
            return httpx.Response(200, json=session)
        if self.search_status != 200:
            return httpx.Response(self.search_status, text="<html>blocked</html>")
        return httpx.Response(200, json={"posts": [POST]})

    def make_client(self, base_url, *, access_jwt=None, timeout=10.0):
        headers = {"Authorization": f"Bearer {access_jwt}"} if access_jwt else {}
        return httpx.Client(
            base_url=base_url, headers=headers, transport=httpx.MockTransport(self.handler)
        )

    def searches(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path.endswith("searchPosts")]


@pytest.fixture
def stored(monkeypatch):
    """Replace the database: two hashtag subscriptions; record what is stored."""
    calls: list[int] = []

    def store_posts(connection, subscription_id, posts):
        calls.append(subscription_id)
        return store.StoreResult(new_posts=len(posts), new_links=len(posts))

    monkeypatch.setattr(store, "subscriptions", lambda connection, kind: list(SUBSCRIPTIONS))
    monkeypatch.setattr(store, "store_posts", store_posts)
    return calls


@pytest.fixture
def fake(monkeypatch):
    def install(**statuses) -> FakeBluesky:
        fake_bluesky = FakeBluesky(**statuses)
        monkeypatch.setattr(bluesky, "make_client", fake_bluesky.make_client)
        return fake_bluesky

    return install


CREDENTIALS = bluesky.Credentials(identifier="me.bsky.social", app_password="abcd-efgh")


def test_no_hashtag_subscriptions_spends_no_login(monkeypatch, fake):
    monkeypatch.setattr(store, "subscriptions", lambda connection, kind: [])
    bsky = fake()

    assert ingestor.run_hashtags(None, settings(CREDENTIALS)) == 0
    assert bsky.requests == []


def test_without_credentials_searches_the_appview_unauthenticated(stored, fake):
    bsky = fake()

    assert ingestor.run_hashtags(None, settings(None)) == 0

    assert [r.url.host for r in bsky.requests] == ["api.test", "api.test"]
    assert all("Authorization" not in r.headers for r in bsky.requests)
    assert stored == [1, 2]


def test_a_blocked_unauthenticated_search_is_a_warning_not_a_failure(stored, fake, caplog):
    bsky = fake(search_status=403)

    assert ingestor.run_hashtags(None, settings(None)) == 0

    # Stops at the first 403 instead of repeating the same request.
    assert len(bsky.searches()) == 1
    assert stored == []
    assert "blocking unauthenticated search" in caplog.text


def test_with_credentials_logs_in_and_searches_through_the_pds(stored, fake):
    bsky = fake()

    assert ingestor.run_hashtags(None, settings(CREDENTIALS)) == 0

    login, *searches = bsky.requests
    assert login.url.host == "entryway.test"
    assert [r.url.host for r in searches] == ["morel.us-east.host.bsky.network"] * 2
    assert all(r.headers["Authorization"] == "Bearer access" for r in searches)
    assert stored == [1, 2]


def test_rejected_credentials_fail_every_hashtag(stored, fake):
    bsky = fake(login_status=401)

    assert ingestor.run_hashtags(None, settings(CREDENTIALS)) == 2

    assert bsky.searches() == []
    assert stored == []


def test_a_403_with_credentials_is_a_failure(stored, fake):
    fake(search_status=403)

    assert ingestor.run_hashtags(None, settings(CREDENTIALS)) == 2
