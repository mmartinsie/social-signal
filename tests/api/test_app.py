"""The UI and the JSON API (D25), with the database replaced by a fake
store."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from socialsignal_api.app import Window, ago, create_app
from socialsignal_api.store import Subscription, Summary, Unavailable

NOW = datetime.now(UTC)
HOST = "testserver"


def summary(**overrides) -> Summary:
    values = {
        "dominant_label": "neutral",
        "positive": 7,
        "neutral": 42,
        "negative": 1,
        "item_count": 50,
        "text": "Mostly neutral posts about Python releases.",
        "updated_at": NOW - timedelta(minutes=5),
    }
    return Summary(**(values | overrides))


def subscription(id_, kind, value, *, has_posts=True, summary=None) -> Subscription:
    return Subscription(id_, kind, value, NOW - timedelta(days=1), has_posts, summary)


class FakeStore:
    def __init__(self, subscriptions=(), down=False):
        self.rows = list(subscriptions)
        self.down = down
        self.subscribed: list[tuple[str, str]] = []
        self.unsubscribed: list[int] = []

    def _check(self):
        if self.down:
            raise Unavailable("connection refused")

    def subscriptions(self):
        self._check()
        return self.rows

    def subscribe(self, kind, value):
        self._check()
        self.subscribed.append((kind, value))
        existing = next((s for s in self.rows if (s.kind, s.value) == (kind, value)), None)
        if existing:
            return existing.id, False
        return 99, True

    def unsubscribe(self, subscription_id):
        self._check()
        self.unsubscribed.append(subscription_id)
        return any(s.id == subscription_id for s in self.rows)


def client(store: FakeStore) -> TestClient:
    return TestClient(create_app(store, Window(max_posts=50, days=7)))


PYTHON = subscription(12, "hashtag", "python", summary=summary())


def test_the_page_shows_label_counts_items_sentence_and_update_time():
    page = client(FakeStore([PYTHON])).get("/")

    assert page.status_code == 200
    html = page.text
    assert "#python" in html
    assert 'class="badge neutral"' in html
    assert "7 positive · 42 neutral · 1 negative" in html
    assert ">50<" in html
    assert "Mostly neutral posts about Python releases." in html
    assert "5 min ago" in html
    assert "last 50 posts of the last 7 days" in html
    # No external assets: the page must work in an isolated network.
    assert "http://" not in html and "https://" not in html


def test_the_llm_sentence_is_escaped():
    attack = '<script>alert("x")</script>'
    store = FakeStore([subscription(1, "hashtag", "x", summary=summary(text=attack))])

    html = client(store).get("/").text

    assert attack not in html
    assert "&lt;script&gt;" in html


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (subscription(1, "handle", "nobody.example", has_posts=False), "Waiting for the first posts"),
        (subscription(2, "hashtag", "new"), "being analysed"),
        (
            subscription(3, "handle", "quiet.example", summary=summary(
                dominant_label=None, positive=0, neutral=0, negative=0, item_count=0, text=None
            )),
            "No posts in the last 7 days",
        ),
        (subscription(4, "hashtag", "x", summary=summary(text=None)), "No summary sentence"),
    ],
)
def test_each_state_is_explained(row, expected):
    assert expected in client(FakeStore([row])).get("/").text


def test_subscribe_from_the_form_normalises_and_redirects():
    store = FakeStore()

    response = client(store).post(
        "/subscriptions", data={"kind": "handle", "value": "@BSKY.app"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert store.subscribed == [("handle", "bsky.app")]


def test_an_invalid_value_is_explained_and_kept_in_the_form():
    store = FakeStore()

    response = client(store).post("/subscriptions", data={"kind": "hashtag", "value": "two words"})

    assert response.status_code == 400
    assert "is not a hashtag" in response.text
    assert 'value="two words"' in response.text
    assert store.subscribed == []


def test_unsubscribe_from_the_form():
    store = FakeStore([PYTHON])

    response = client(store).post("/subscriptions/12/delete", follow_redirects=False)

    assert response.status_code == 303
    assert store.unsubscribed == [12]


def test_api_lists_subscriptions_with_their_summary():
    body = client(FakeStore([PYTHON])).get("/api/subscriptions").json()

    assert body[0]["kind"] == "hashtag" and body[0]["value"] == "python"
    assert body[0]["summary"]["dominant_label"] == "neutral"
    assert body[0]["summary"]["counts"] == {"positive": 7, "neutral": 42, "negative": 1}
    assert body[0]["summary"]["item_count"] == 50


def test_api_subscribe_is_201_then_200():
    store = FakeStore([PYTHON])
    api = client(store)

    created = api.post("/api/subscriptions", json={"kind": "handle", "value": "bsky.app"})
    existing = api.post("/api/subscriptions", json={"kind": "hashtag", "value": "#Python"})

    assert created.status_code == 201 and created.json()["created"] is True
    assert existing.status_code == 200 and existing.json()["id"] == 12


@pytest.mark.parametrize(
    "body", [{"kind": "handle", "value": "not a handle"}, {"kind": "list", "value": "x"}, {}]
)
def test_api_refuses_invalid_subscriptions(body):
    assert client(FakeStore()).post("/api/subscriptions", json=body).status_code == 422


def test_api_unsubscribe_is_204_then_404():
    api = client(FakeStore([PYTHON]))

    assert api.delete("/api/subscriptions/12").status_code == 204
    assert api.delete("/api/subscriptions/13").status_code == 404


def test_a_cross_site_post_is_refused():
    store = FakeStore()

    response = client(store).post(
        "/subscriptions",
        data={"kind": "handle", "value": "bsky.app"},
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert store.subscribed == []


def test_a_same_origin_post_is_accepted():
    store = FakeStore()

    response = client(store).post(
        "/subscriptions",
        data={"kind": "handle", "value": "bsky.app"},
        headers={"Origin": f"http://{HOST}"},
        follow_redirects=False,
    )

    assert response.status_code == 303


def test_a_database_outage_is_a_503_page_that_says_so():
    response = client(FakeStore(down=True)).get("/")

    assert response.status_code == 503
    assert "database is not reachable" in response.text


def test_a_database_outage_is_a_503_in_the_api():
    response = client(FakeStore(down=True)).get("/api/subscriptions")

    assert response.status_code == 503


def test_probes_do_not_touch_the_database():
    api = client(FakeStore(down=True))

    assert api.get("/healthz").status_code == 200
    assert api.get("/readyz").status_code == 200


def test_no_swagger_ui_from_a_cdn():
    assert client(FakeStore()).get("/docs").status_code == 404


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(seconds=20), "just now"),
        (timedelta(minutes=5), "5 min ago"),
        (timedelta(hours=3), "3 h ago"),
        (timedelta(days=1), "1 day ago"),
        (timedelta(days=4), "4 days ago"),
    ],
)
def test_relative_times(delta, expected):
    assert ago(NOW - delta, NOW) == expected
