"""The ingestor refuses settings that Bluesky would reject or silently ignore,
and reads the optional credentials from the mounted Secret."""

from pathlib import Path

import pytest

from socialsignal_ingestor.__main__ import IngestorSettings, load_credentials


def test_defaults_match_the_agreed_design(tmp_path):
    settings = IngestorSettings.from_env({"BLUESKY_CREDENTIALS_DIR": str(tmp_path / "none")})

    assert settings.public_api_url == "https://public.api.bsky.app"
    assert settings.search_api_url == "https://api.bsky.app"
    assert settings.entryway_url == "https://bsky.social"
    assert settings.posts_per_handle == 50
    assert settings.posts_per_hashtag == 50
    assert settings.author_feed_filter == "posts_and_author_threads"
    assert settings.credentials is None


@pytest.mark.parametrize("name", ["INGEST_POSTS_PER_HANDLE", "INGEST_POSTS_PER_HASHTAG"])
@pytest.mark.parametrize("limit", ["0", "101"])
def test_rejects_a_limit_outside_bluesky_range(name, limit):
    with pytest.raises(ValueError, match=name):
        IngestorSettings.from_env({name: limit})


def test_rejects_an_unknown_filter():
    # Bluesky would ignore it and return replies to other accounts.
    with pytest.raises(ValueError, match="INGEST_AUTHOR_FEED_FILTER"):
        IngestorSettings.from_env({"INGEST_AUTHOR_FEED_FILTER": "posts_and_author_thread"})


def write(directory: Path, **files: str) -> Path:
    directory.mkdir(exist_ok=True)
    for name, content in files.items():
        (directory / name.replace("_", "-")).write_text(content)
    return directory


def test_no_credentials_without_the_secret(tmp_path):
    # The Secret is optional: missing, its volume is an empty directory.
    assert load_credentials(tmp_path / "missing") is None
    assert load_credentials(write(tmp_path / "empty")) is None
    assert load_credentials(write(tmp_path / "blank", identifier="", app_password="\n")) is None


def test_reads_both_credentials_and_strips_newlines(tmp_path):
    directory = write(tmp_path / "s", identifier="me.bsky.social\n", app_password="abcd-efgh\n")

    credentials = load_credentials(directory)

    assert credentials.identifier == "me.bsky.social"
    assert credentials.app_password == "abcd-efgh"


@pytest.mark.parametrize("present", [{"identifier": "me"}, {"app_password": "abcd"}])
def test_only_one_credential_is_an_error(tmp_path, present):
    with pytest.raises(ValueError, match="needs both"):
        load_credentials(write(tmp_path / "s", **present))
