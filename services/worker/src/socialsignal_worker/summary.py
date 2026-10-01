"""The deterministic part of a summary (A3): the count per label and the
dominant label, computed from the stored per-post labels, never by the LLM.
"""

from collections.abc import Iterable
from dataclasses import dataclass

LABELS = ("positive", "neutral", "negative")


@dataclass(frozen=True)
class Counts:
    positive: int = 0
    neutral: int = 0
    negative: int = 0

    @classmethod
    def of(cls, labels: Iterable[str]) -> "Counts":
        values = dict.fromkeys(LABELS, 0)
        for label in labels:
            values[label] += 1  # KeyError on anything else: the schema allows only these
        return cls(**values)

    @property
    def total(self) -> int:
        return self.positive + self.neutral + self.negative

    def as_dict(self) -> dict[str, int]:
        return {"positive": self.positive, "neutral": self.neutral, "negative": self.negative}


def dominant_label(counts: Counts) -> str | None:
    """The label with the most posts; None without posts.

    A tie is `neutral` (author's decision, A3): a tie between positive and
    negative is no clear sentiment either way, and a tie with neutral never
    claims more sentiment than the data supports. The counts are shown next
    to the label, so the split stays visible.
    """
    if counts.total == 0:
        return None
    values = counts.as_dict()
    top = max(values.values())
    winners = [label for label, count in values.items() if count == top]
    return winners[0] if len(winners) == 1 else "neutral"
