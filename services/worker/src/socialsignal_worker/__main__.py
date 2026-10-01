"""Entry point of the summary worker CronJob:

    python -m socialsignal_worker

One run brings every subscription's summary up to date (A3, D24):
  1. it classifies, once, the posts of the subscription's window (A2) that
     have no label yet (A9);
  2. once every post of the window has a label, it counts them and picks
     the dominant label;
  3. only if the posts changed, it asks the LLM for a new sentence and
     stores the summary, with updated_at = now.

Subscriptions whose summary is oldest go first. After RUN_BUDGET_SECONDS no
new LLM call starts, so the run ends before the Job's deadline; the next run
picks up what is left. The labels already stored are never lost.

Exit status:
  0  every subscription is up to date, or was left for the next run because
     the time budget was used up.
  1  the LLM was not ready or stopped answering, or at least one
     subscription failed, so the failed Job is visible in `kubectl get jobs`.
"""

import logging
import os
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import httpx
import psycopg

from socialsignal_common.db import DatabaseSettings, connect
from socialsignal_worker import llm, store
from socialsignal_worker.summary import Counts, dominant_label

log = logging.getLogger("socialsignal_worker")

Clock = Callable[[], float]


@dataclass(frozen=True)
class WorkerSettings:
    llm_url: str
    # "Recent" (A2): the last summary_max_posts posts of the last
    # summary_window_days days.
    summary_max_posts: int
    summary_window_days: int
    # The sentence reads only the sentence_posts most recent posts, each cut
    # to sentence_post_chars characters: on CPU its time grows with the
    # prompt (D22, D24).
    sentence_posts: int
    sentence_post_chars: int
    # No new LLM call starts after run_budget_seconds. The budget plus the
    # longest call must stay below the Job's activeDeadlineSeconds.
    run_budget_seconds: int
    classify_timeout_seconds: int
    sentence_timeout_seconds: int

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> "WorkerSettings":
        def number(name: str, default: int) -> int:
            value = int(environ.get(name, str(default)))
            if value < 1:
                raise ValueError(f"{name} must be a positive integer")
            return value

        return cls(
            llm_url=environ.get("LLM_URL", "http://127.0.0.1:8080"),
            summary_max_posts=number("SUMMARY_MAX_POSTS", 50),
            summary_window_days=number("SUMMARY_WINDOW_DAYS", 7),
            sentence_posts=number("SENTENCE_POSTS", 20),
            sentence_post_chars=number("SENTENCE_POST_CHARS", 280),
            run_budget_seconds=number("RUN_BUDGET_SECONDS", 180),
            classify_timeout_seconds=number("CLASSIFY_TIMEOUT_SECONDS", 30),
            sentence_timeout_seconds=number("SENTENCE_TIMEOUT_SECONDS", 90),
        )


def update_subscription(
    connection: psycopg.Connection,
    client: httpx.Client,
    settings: WorkerSettings,
    model: str,
    subscription: store.Subscription,
    deadline: float,
    clock: Clock,
) -> bool:
    """Bring one subscription's summary up to date.

    Returns False if the time budget ran out first. Raises llm.Unavailable
    if the LLM stops answering while classifying, llm.BadAnswer if it gives
    an unusable label, and psycopg.Error on a database error.
    """
    name = subscription.name
    posts = store.window(
        connection, subscription.id, settings.summary_max_posts, settings.summary_window_days
    )
    labels = []
    classified = 0
    started = clock()
    for post in posts:
        label = post.label
        if label is None:
            if clock() >= deadline:
                log.info(
                    "%s: time budget used up; %d posts classified, %d left for the next run",
                    name,
                    classified,
                    sum(p.label is None for p in posts) - classified,
                )
                return False
            label = llm.classify(client, post.text, timeout=settings.classify_timeout_seconds)
            # Stored at once: a run cut short keeps what it classified.
            store.save_label(connection, post.uri, label, model)
            classified += 1
        labels.append(label)
    if classified:
        log.info("%s: classified %d posts in %.0f s", name, classified, clock() - started)

    counts = Counts.of(labels)
    dominant = dominant_label(counts)
    current = store.current_summary(connection, subscription.id)
    # The posts changed if one was classified since the summary was written
    # (new, or new to this subscription) or if the counts moved (a post left
    # the window). Not caught: a post classified earlier for another
    # subscription replacing one with the same label in a full window.
    changed = (
        current is None
        or classified > 0
        or current.counts != counts
        or any(p.classified_at and p.classified_at > current.updated_at for p in posts)
    )
    # A sentence that failed last time is retried, even with the same posts.
    sentence_missing = current is not None and current.summary_text is None and counts.total > 0
    if not changed and not sentence_missing:
        log.info("%s: unchanged, %d posts", name, counts.total)
        return True

    text = None
    finished = True
    if counts.total > 0:
        if clock() >= deadline:
            log.info("%s: time budget used up; the sentence is left for the next run", name)
            finished = False
        else:
            text = sentence(client, settings, subscription, counts, dominant, posts, clock)
    if not changed and text is None:
        # Nothing new to store: the sentence is still missing, retry later.
        return finished

    try:
        store.write_summary(connection, subscription.id, counts, dominant, text)
    except psycopg.errors.ForeignKeyViolation:
        log.info("%s: unsubscribed during the run, nothing stored", name)
        return finished
    log.info(
        "%s: summary of %d posts: %d positive, %d neutral, %d negative -> %s; %s",
        name,
        counts.total,
        counts.positive,
        counts.neutral,
        counts.negative,
        dominant or "no label",
        "with a sentence" if text else "no sentence",
    )
    return finished


def sentence(
    client: httpx.Client,
    settings: WorkerSettings,
    subscription: store.Subscription,
    counts: Counts,
    dominant: str | None,
    posts: list[store.WindowPost],
    clock: Clock,
) -> str | None:
    """The LLM's sentence, or None if it could not be written.

    Without it the summary is still stored with its label and counts
    (degraded mode, A3); an old sentence would describe other posts.
    """
    started = clock()
    try:
        text = llm.write_sentence(
            client,
            subscription.name,
            counts,
            dominant or "none",
            [post.text for post in posts[: settings.sentence_posts]],
            post_chars=settings.sentence_post_chars,
            timeout=settings.sentence_timeout_seconds,
        )
    except llm.LLMError as error:
        log.warning("%s: no sentence, it is retried next run: %s", subscription.name, error)
        return None
    log.info("%s: sentence written in %.0f s", subscription.name, clock() - started)
    return text


def run(
    connection: psycopg.Connection,
    client: httpx.Client,
    settings: WorkerSettings,
    model: str,
    clock: Clock = time.monotonic,
) -> int:
    """Update every subscription's summary. Returns how many failed."""
    deadline = clock() + settings.run_budget_seconds
    subscriptions = store.subscriptions(connection)
    log.info("%d subscriptions", len(subscriptions))
    failed = 0
    for index, subscription in enumerate(subscriptions):
        try:
            finished = update_subscription(
                connection, client, settings, model, subscription, deadline, clock
            )
        except llm.Unavailable as error:
            log.error(
                "%s: the LLM stopped answering (%s); %d subscriptions left for the next run",
                subscription.name,
                error,
                len(subscriptions) - index,
            )
            return failed + 1
        except llm.BadAnswer as error:
            log.error("%s: %s", subscription.name, error)
            failed += 1
            continue
        except psycopg.Error as error:
            log.error("%s: database error: %s", subscription.name, error)
            failed += 1
            continue
        if not finished:
            left = len(subscriptions) - index - 1
            if left:
                log.info("time budget used up: %d more subscriptions left for the next run", left)
            break
    return failed


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # httpx logs every request at INFO; our own lines already say enough.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = WorkerSettings.from_env()
    database = DatabaseSettings.from_env()

    with llm.make_client(settings.llm_url) as client:
        # Right after a start or an LLM update the model takes about 40 s to
        # load (D23): touch nothing and let the next run retry.
        if not llm.is_ready(client):
            log.error("the LLM at %s is not ready: nothing done", settings.llm_url)
            return 1
        try:
            model = llm.model_name(client)
        except llm.LLMError as error:
            log.error("the LLM at %s: %s", settings.llm_url, error)
            return 1
        with connect(database, application_name="socialsignal-worker") as connection:
            failed = run(connection, client, settings, model)

    if failed:
        log.error("%d subscriptions failed", failed)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
