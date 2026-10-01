"""Evaluate the LLM image offline: label validity, accuracy on a small
hand-labelled set, latency, and optionally real posts and one summary
sentence (D22, D24).

It uses the worker's own client (socialsignal_worker.llm), so it measures
exactly the prompts and output format the worker sends. Run the LLM with no
network at all, then run this script in the worker image, sharing the LLM
container's network namespace. Replace the tags with those in
dist/images/<arch>/app/images.txt:

    docker run -d --name llm-eval --network none --read-only --cap-drop ALL \
      socialsignal/llm:<tag> --threads 4 --ctx-size 8192 --parallel 1 --reasoning off
    docker run --rm --network container:llm-eval -v "$PWD/tools:/tools:ro" \
      socialsignal/worker:<tag> python /tools/llm_eval.py
    docker rm -f llm-eval

Options: --real FILE labels real posts from a JSON list of {"source", "text"}
objects; --summary times one summary sentence over them, the way the worker
writes it (needs --real).

This is a smoke check, not a benchmark: 16 examples can show that the model
is useless, not how accurate it is. A real evaluation set is an open item.
"""

import argparse
import json
import statistics
import time

import httpx

from socialsignal_worker import llm
from socialsignal_worker.summary import Counts, dominant_label

# The worker's defaults (values.yaml): the sentence reads the 20 most recent
# posts, each cut to 280 characters.
SENTENCE_POSTS = 20
SENTENCE_POST_CHARS = 280

# (expected label, text). "mixed" has no single right answer and is not
# counted in the accuracy.
LABELLED = [
    ("positive", "Just got the job offer I've been dreaming about for years. I can't stop smiling!"),
    ("positive", "The new update is fantastic, everything feels so much faster. Great work, team!"),
    ("positive", "¡Qué concierto tan increíble anoche! Volvería mañana mismo."),
    ("positive", "Our volunteers planted 500 trees this weekend. So proud of this community."),
    ("negative", "My flight was cancelled again and nobody at the desk can tell us anything. "
                 "Absolutely furious."),
    ("negative", "This app crashes every time I open it. Worst update ever."),
    ("negative", "Oh great, another Monday meeting that could have been an email. "
                 "Just what I needed."),
    ("negative", "Wow, only three hours on hold with customer support. "
                 "Truly world-class service."),
    # Known hard case (D22): the same sarcasm without the explicit complaint
    # context came out positive with Gemma 4 E2B.
    ("negative", "Wow, only three hours on hold. Truly world-class service."),
    ("negative", "El servicio de trenes es un desastre, llevo una hora esperando sin ninguna "
                 "información."),
    ("neutral", "The city council meets on Thursday at 7 pm to discuss the new budget."),
    ("neutral", "Python 3.14 was released today. The changelog is available on the official website."),
    ("neutral", "Does anyone know if the library is open on Sunday?"),
    ("neutral", "Temperatures will range between 12 and 18 degrees this weekend."),
    ("neutral", "Reminder: the submission deadline is Friday at noon."),
    ("mixed", "The food was great but the service was painfully slow."),
]


def classify(client: httpx.Client, text: str) -> tuple[str, float]:
    start = time.perf_counter()
    label = llm.classify(client, text, timeout=300)
    return label, time.perf_counter() - start


def wait_until_ready(client: httpx.Client) -> None:
    """/health answers 503 while the model loads and 200 when it is ready."""
    start = time.perf_counter()
    while True:
        try:
            if client.get("/health").status_code == 200:
                break
        except httpx.TransportError:
            pass
        time.sleep(0.5)
    models = [m["id"] for m in client.get("/v1/models").json()["data"]]
    print(f"ready after {time.perf_counter() - start:.1f} s of waiting; models: {models}")


def evaluate_labelled(client: httpx.Client, latencies: list[float]) -> None:
    print("\n--- labelled set")
    correct = total = 0
    for expected, text in LABELLED:
        label, elapsed = classify(client, text)
        latencies.append(elapsed)
        if expected != "mixed":
            total += 1
            correct += label == expected
        mark = "  " if expected in ("mixed", label) else "XX"
        print(f"{mark} {elapsed:5.2f}s expected={expected:8} got={label:8} {text[:60]!r}")
    print(f"accuracy {correct}/{total}")


def evaluate_real(client: httpx.Client, posts: list[dict], latencies: list[float]) -> Counts:
    print("\n--- real posts")
    labels = []
    for post in posts:
        label, elapsed = classify(client, post["text"])
        latencies.append(elapsed)
        labels.append(label)
        print(f"   {elapsed:5.2f}s {label:8} [{post['source']}] {post['text'][:70]!r}")
    counts = Counts.of(labels)
    print("label counts:", counts.as_dict())
    return counts


def time_sentence(client: httpx.Client, posts: list[dict], counts: Counts) -> None:
    """One summary sentence, written exactly as the worker writes it."""
    start = time.perf_counter()
    sentence = llm.write_sentence(
        client,
        "#evaluation",
        counts,
        dominant_label(counts) or "none",
        [post["text"] for post in posts[:SENTENCE_POSTS]],
        post_chars=SENTENCE_POST_CHARS,
        timeout=600,
    )
    elapsed = time.perf_counter() - start
    print(f"\nsentence over {min(len(posts), SENTENCE_POSTS)} posts: {elapsed:.1f}s")
    print("sentence:", sentence)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--real", help='JSON list of {"source", "text"} objects')
    parser.add_argument("--summary", action="store_true", help="time one summary sentence")
    args = parser.parse_args()
    posts = json.load(open(args.real)) if args.real else []

    with httpx.Client(base_url=args.url, timeout=300) as client:
        wait_until_ready(client)
        classify(client, "Hello world.")  # warm-up: the first request pays one-off costs
        latencies: list[float] = []
        evaluate_labelled(client, latencies)
        counts = evaluate_real(client, posts, latencies) if posts else Counts()
        print(
            f"\nper-post latency: median {statistics.median(latencies):.2f}s, "
            f"max {max(latencies):.2f}s over {len(latencies)} posts"
        )
        if args.summary and posts:
            time_sentence(client, posts, counts)


if __name__ == "__main__":
    main()
