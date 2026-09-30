"""The ingestor refuses settings that Bluesky would reject or silently ignore."""

import pytest

from socialsignal_ingestor.__main__ import IngestorSettings


def test_defaults_match_the_agreed_design():
    settings = IngestorSettings.from_env({})

    assert settings.bluesky_url == "https://public.api.bsky.app"
    assert settings.posts_per_handle == 50
    assert settings.author_feed_filter == "posts_and_author_threads"


@pytest.mark.parametrize("limit", ["0", "101"])
def test_rejects_a_limit_outside_bluesky_range(limit):
    with pytest.raises(ValueError, match="INGEST_POSTS_PER_HANDLE"):
        IngestorSettings.from_env({"INGEST_POSTS_PER_HANDLE": limit})


def test_rejects_an_unknown_filter():
    # Bluesky would ignore it and return replies to other accounts.
    with pytest.raises(ValueError, match="INGEST_AUTHOR_FEED_FILTER"):
        IngestorSettings.from_env({"INGEST_AUTHOR_FEED_FILTER": "posts_and_author_thread"})
