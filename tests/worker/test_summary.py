"""The dominant label: the most frequent one, and `neutral` on any tie (A3)."""

import pytest

from socialsignal_worker.summary import Counts, dominant_label


def test_counts_each_label():
    counts = Counts.of(["positive", "negative", "neutral", "negative"])

    assert counts == Counts(positive=1, neutral=1, negative=2)
    assert counts.total == 4


def test_rejects_an_unknown_label():
    with pytest.raises(KeyError):
        Counts.of(["mixed"])


def test_no_posts_have_no_label():
    assert dominant_label(Counts()) is None


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        (Counts(positive=3, neutral=1, negative=1), "positive"),
        (Counts(positive=1, neutral=3, negative=1), "neutral"),
        (Counts(positive=1, neutral=1, negative=3), "negative"),
        (Counts(negative=1), "negative"),
    ],
)
def test_a_single_maximum_wins(counts, expected):
    assert dominant_label(counts) == expected


@pytest.mark.parametrize(
    "counts",
    [
        Counts(positive=5, neutral=2, negative=5),  # good and bad
        Counts(positive=5, neutral=5, negative=2),  # good and neutral
        Counts(positive=2, neutral=5, negative=5),  # bad and neutral
        Counts(positive=4, neutral=4, negative=4),  # all three
    ],
)
def test_any_tie_is_neutral(counts):
    assert dominant_label(counts) == "neutral"
