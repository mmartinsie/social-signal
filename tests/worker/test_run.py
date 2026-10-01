"""One worker run (D24): what it classifies, when it rewrites a summary, and
how it behaves when the time budget runs out or the LLM fails.

The database is replaced by a fake of the store module, the LLM by fakes of
llm.classify and llm.write_sentence, and time by a clock the fake LLM
advances.
"""

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from socialsignal_worker import __main__ as worker
from socialsignal_worker import llm, store
from socialsignal_worker.store import Subscription, Summary, WindowPost
from socialsignal_worker.summary import Counts

MODEL = "gemma-4-E2B-it-qat-q4_0"
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
PYTHON = Subscription(id=1, kind="hashtag", value="python")
BSKY = Subscription(id=2, kind="handle", value="bsky.app")


def post(n: int, label: str | None = None, classified_at: datetime | None = None) -> WindowPost:
    return WindowPost(
        uri=f"at://did:plc:a/app.bsky.feed.post/{n}",
        text=f"post {n}",
        label=label,
        classified_at=classified_at or (T0 if label else None),
    )


def settings(**overrides) -> worker.WorkerSettings:
    values = {
        "llm_url": "http://llm.test",
        "summary_max_posts": 50,
        "summary_window_days": 7,
        "sentence_posts": 20,
        "sentence_post_chars": 280,
        "run_budget_seconds": 180,
        "classify_timeout_seconds": 30,
        "sentence_timeout_seconds": 90,
    }
    return worker.WorkerSettings(**(values | overrides))


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeStore:
    def __init__(self, windows, summaries=None):
        self.windows = windows  # {Subscription: [WindowPost]}
        self.summaries = summaries or {}  # {subscription id: Summary}
        self.labels: list[tuple[str, str, str]] = []
        self.written: dict[int, tuple[Counts, str | None, str | None]] = {}
        self.errors: dict[int, Exception] = {}  # raised by window()
        self.write_errors: dict[int, Exception] = {}  # raised by write_summary()

    def install(self, monkeypatch):
        monkeypatch.setattr(store, "subscriptions", lambda connection: list(self.windows))
        monkeypatch.setattr(store, "window", self.window)
        monkeypatch.setattr(store, "save_label", self.save_label)
        monkeypatch.setattr(store, "current_summary", lambda c, sid: self.summaries.get(sid))
        monkeypatch.setattr(store, "write_summary", self.write_summary)
        return self

    def window(self, connection, subscription_id, limit, days):
        if subscription_id in self.errors:
            raise self.errors[subscription_id]
        posts = next(p for s, p in self.windows.items() if s.id == subscription_id)
        return posts[:limit]

    def save_label(self, connection, post_uri, label, model):
        self.labels.append((post_uri, label, model))

    def write_summary(self, connection, subscription_id, counts, dominant, text):
        if subscription_id in self.write_errors:
            raise self.write_errors[subscription_id]
        self.written[subscription_id] = (counts, dominant, text)


class FakeLLM:
    def __init__(self, clock, labels=None, seconds_per_call=3.0):
        self.clock = clock
        self.labels = labels or {}  # {text: label or exception}
        self.seconds_per_call = seconds_per_call
        self.classified: list[str] = []
        self.sentences: list[list[str]] = []
        self.sentence_error: Exception | None = None

    def install(self, monkeypatch):
        monkeypatch.setattr(llm, "classify", self.classify)
        monkeypatch.setattr(llm, "write_sentence", self.write_sentence)
        return self

    def classify(self, client, text, *, timeout):
        self.clock.now += self.seconds_per_call
        result = self.labels.get(text, "neutral")
        if isinstance(result, Exception):
            raise result
        self.classified.append(text)
        return result

    def write_sentence(self, client, subscription, counts, dominant, texts, *, post_chars, timeout):
        self.clock.now += self.seconds_per_call
        if self.sentence_error:
            raise self.sentence_error
        self.sentences.append(list(texts))
        return f"Sentence about {subscription}."


@pytest.fixture
def clock():
    return Clock()


def run(clock, **overrides) -> int:
    return worker.run(None, None, settings(**overrides), MODEL, clock=clock)


def test_settings_defaults_match_the_agreed_design():
    assert worker.WorkerSettings.from_env({}) == settings(llm_url="http://127.0.0.1:8080")


@pytest.mark.parametrize("name", ["RUN_BUDGET_SECONDS", "SUMMARY_MAX_POSTS", "SENTENCE_POSTS"])
def test_settings_reject_zero(name):
    with pytest.raises(ValueError, match=name):
        worker.WorkerSettings.from_env({name: "0"})


def test_classifies_only_unlabelled_posts_and_writes_the_summary(monkeypatch, clock):
    posts = [post(3), post(2), post(1, "negative")]
    fake = FakeStore({PYTHON: posts}).install(monkeypatch)
    model = FakeLLM(clock, labels={"post 3": "positive", "post 2": "negative"}).install(monkeypatch)

    assert run(clock) == 0

    assert model.classified == ["post 3", "post 2"]
    assert fake.labels == [(posts[0].uri, "positive", MODEL), (posts[1].uri, "negative", MODEL)]
    assert fake.written == {
        1: (Counts(positive=1, negative=2), "negative", "Sentence about #python.")
    }


def test_the_sentence_reads_only_the_most_recent_posts(monkeypatch, clock):
    FakeStore({PYTHON: [post(3), post(2), post(1)]}).install(monkeypatch)
    model = FakeLLM(clock).install(monkeypatch)

    run(clock, sentence_posts=2)

    assert model.sentences == [["post 3", "post 2"]]


def test_an_unchanged_summary_is_not_rewritten(monkeypatch, clock):
    summary = Summary(Counts(positive=1, neutral=1), "Old sentence.", T0 + timedelta(minutes=5))
    fake = FakeStore(
        {PYTHON: [post(2, "positive"), post(1, "neutral")]}, {1: summary}
    ).install(monkeypatch)
    model = FakeLLM(clock).install(monkeypatch)

    assert run(clock) == 0

    assert fake.written == {}
    assert model.classified == [] and model.sentences == []


def test_a_post_leaving_the_window_changes_the_summary(monkeypatch, clock):
    summary = Summary(Counts(positive=1, neutral=1), "Old sentence.", T0 + timedelta(minutes=5))
    fake = FakeStore({PYTHON: [post(2, "positive")]}, {1: summary}).install(monkeypatch)
    FakeLLM(clock).install(monkeypatch)

    run(clock)

    assert fake.written == {1: (Counts(positive=1), "positive", "Sentence about #python.")}


def test_a_post_labelled_after_the_summary_changes_it_even_with_equal_counts(monkeypatch, clock):
    # Post 3 was classified for another subscription after this summary was
    # written, and replaced post 1 (same label) in this subscription's window.
    summary = Summary(Counts(positive=2), "Old sentence.", T0 + timedelta(minutes=5))
    later = T0 + timedelta(minutes=10)
    fake = FakeStore(
        {PYTHON: [post(3, "positive", later), post(2, "positive")]}, {1: summary}
    ).install(monkeypatch)
    FakeLLM(clock).install(monkeypatch)

    run(clock)

    assert fake.written == {1: (Counts(positive=2), "positive", "Sentence about #python.")}


def test_a_failed_sentence_keeps_the_label_and_counts(monkeypatch, clock):
    fake = FakeStore({PYTHON: [post(1)], BSKY: [post(2)]}).install(monkeypatch)
    model = FakeLLM(clock).install(monkeypatch)
    model.sentence_error = llm.Unavailable("ReadTimeout")

    # Degraded mode (A3), not a failure: the run goes on and succeeds.
    assert run(clock) == 0

    assert fake.written == {
        1: (Counts(neutral=1), "neutral", None),
        2: (Counts(neutral=1), "neutral", None),
    }


def test_a_missing_sentence_is_retried_with_the_same_posts(monkeypatch, clock):
    summary = Summary(Counts(neutral=1), None, T0 + timedelta(minutes=5))
    fake = FakeStore({PYTHON: [post(1, "neutral")]}, {1: summary}).install(monkeypatch)
    FakeLLM(clock).install(monkeypatch)

    run(clock)

    assert fake.written == {1: (Counts(neutral=1), "neutral", "Sentence about #python.")}


def test_a_sentence_that_fails_again_rewrites_nothing(monkeypatch, clock):
    summary = Summary(Counts(neutral=1), None, T0 + timedelta(minutes=5))
    fake = FakeStore({PYTHON: [post(1, "neutral")]}, {1: summary}).install(monkeypatch)
    model = FakeLLM(clock).install(monkeypatch)
    model.sentence_error = llm.BadAnswer("empty sentence")

    assert run(clock) == 0

    # updated_at only moves when the summary is generated.
    assert fake.written == {}


def test_no_recent_posts_is_a_summary_without_label_or_sentence(monkeypatch, clock):
    fake = FakeStore({BSKY: []}).install(monkeypatch)
    model = FakeLLM(clock).install(monkeypatch)

    run(clock)

    assert fake.written == {2: (Counts(), None, None)}
    assert model.sentences == []


def test_the_budget_stops_before_the_next_llm_call(monkeypatch, clock):
    # 70 s per post and a 180 s budget: calls start at 0, 70 and 140 s.
    fake = FakeStore({PYTHON: [post(n) for n in range(5, 0, -1)], BSKY: [post(9)]}).install(
        monkeypatch
    )
    model = FakeLLM(clock, seconds_per_call=70).install(monkeypatch)

    assert run(clock) == 0

    assert len(fake.labels) == 3  # kept for the next run
    assert fake.written == {}  # never a summary of half the posts
    assert "post 9" not in model.classified


def test_a_budget_used_up_before_the_sentence_stores_the_counts(monkeypatch, clock):
    fake = FakeStore({PYTHON: [post(2), post(1)], BSKY: [post(9)]}).install(monkeypatch)
    model = FakeLLM(clock, seconds_per_call=90).install(monkeypatch)

    run(clock)

    # The counts are fresh; the sentence is retried next run.
    assert fake.written == {1: (Counts(neutral=2), "neutral", None)}
    assert model.sentences == []
    assert "post 9" not in model.classified


def test_a_bad_answer_fails_only_its_subscription(monkeypatch, clock):
    fake = FakeStore({PYTHON: [post(1)], BSKY: [post(2)]}).install(monkeypatch)
    FakeLLM(clock, labels={"post 1": llm.BadAnswer("not a label")}).install(monkeypatch)

    assert run(clock) == 1

    assert list(fake.written) == [2]


def test_a_database_error_fails_only_its_subscription(monkeypatch, clock):
    fake = FakeStore({PYTHON: [post(1)], BSKY: [post(2)]}).install(monkeypatch)
    fake.errors[1] = psycopg.OperationalError("server closed the connection")
    FakeLLM(clock).install(monkeypatch)

    assert run(clock) == 1

    assert list(fake.written) == [2]


def test_an_unavailable_llm_stops_the_run(monkeypatch, clock):
    fake = FakeStore({PYTHON: [post(1)], BSKY: [post(2)]}).install(monkeypatch)
    model = FakeLLM(clock, labels={"post 1": llm.Unavailable("ConnectError")}).install(
        monkeypatch
    )

    assert run(clock) == 1

    assert fake.written == {}
    assert model.classified == []  # BSKY is left for the next run


def test_unsubscribed_during_the_run_is_not_a_failure(monkeypatch, clock):
    fake = FakeStore({PYTHON: [post(1)], BSKY: [post(2)]}).install(monkeypatch)
    fake.write_errors[1] = psycopg.errors.ForeignKeyViolation("subscription deleted")
    FakeLLM(clock).install(monkeypatch)

    assert run(clock) == 0

    assert list(fake.written) == [2]
