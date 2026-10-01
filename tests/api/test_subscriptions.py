"""Subscriptions are stored the way the ingestor expects them: a handle
without "@", a hashtag without "#", lower-case, and in the AT Protocol's
format (D25)."""

import pytest

from socialsignal_api.subscriptions import InvalidSubscription, display_name, normalise


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("bsky.app", "bsky.app"),
        ("@BSKY.app", "bsky.app"),
        ("  jay.bsky.team ", "jay.bsky.team"),
        ("4chan.org", "4chan.org"),  # a label may start with a digit, not the TLD
        ("xn--bcher-kva.example", "xn--bcher-kva.example"),  # punycode
    ],
)
def test_valid_handles_are_normalised(value, expected):
    assert normalise("handle", value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "bsky",  # one label
        "bsky.app.",  # empty label
        "-bsky.app",  # leading hyphen
        "bsky-.app",  # trailing hyphen
        "bsky.123",  # TLD starts with a digit
        "bsky app.com",  # space
        "did:plc:z72i7hdynmk6r22z27h6tvur",  # DIDs are an open item
        "a" * 64 + ".com",  # label over 63
        ("a" * 63 + ".") * 4 + "com",  # over 253
        "",
    ],
)
def test_invalid_handles_are_refused(value):
    with pytest.raises(InvalidSubscription):
        normalise("handle", value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("python", "python"), ("#Python", "python"), ("#españa", "españa"), ("##double", "#double")],
)
def test_valid_hashtags_are_normalised(value, expected):
    assert normalise("hashtag", value) == expected


@pytest.mark.parametrize("value", ["", "#", "two words", "tab\there", "x" * 65])
def test_invalid_hashtags_are_refused(value):
    with pytest.raises(InvalidSubscription):
        normalise("hashtag", value)


def test_unknown_kind_is_refused():
    with pytest.raises(InvalidSubscription, match="kind"):
        normalise("list", "anything")


def test_display_names():
    assert display_name("handle", "bsky.app") == "@bsky.app"
    assert display_name("hashtag", "python") == "#python"
