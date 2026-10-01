"""What analysts may subscribe to, normalised the way the ingestor expects
it (D18, D20): a handle without "@", a hashtag without "#", both lower-case.

The analysis zone has no internet access, so the API cannot ask Bluesky
whether an account or a tag exists: it only checks the format, with the
rules of the AT Protocol. A subscription Bluesky does not know never gets
posts, and the UI keeps showing it as pending (D25).
"""

import re

KINDS = ("handle", "hashtag")

# The AT Protocol's handle syntax (atproto packages/syntax/src/handle.ts):
# a domain name of at least two labels of ASCII letters, digits and
# hyphens, whose last label starts with a letter; at most 253 characters.
HANDLE = re.compile(
    r"^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]([a-z0-9-]{0,61}[a-z0-9])?$"
)
HANDLE_MAX_LENGTH = 253

# The hashtag facet and searchPosts' `tag` (lexicons): at most 64 graphemes
# and 640 bytes. Counting code points is stricter than graphemes, never
# looser.
TAG_MAX_CHARS = 64
TAG_MAX_BYTES = 640


class InvalidSubscription(ValueError):
    pass


def normalise(kind: str, value: str) -> str:
    """The stored form of a subscription, or InvalidSubscription."""
    value = value.strip()
    if kind == "handle":
        handle = value.removeprefix("@").lower()
        if len(handle) > HANDLE_MAX_LENGTH or not HANDLE.match(handle):
            raise InvalidSubscription(
                f"{value!r} is not a Bluesky handle (for example: bsky.app)"
            )
        return handle
    if kind == "hashtag":
        tag = value.removeprefix("#").lower()
        if not tag or any(c.isspace() for c in tag):
            raise InvalidSubscription(
                f"{value!r} is not a hashtag (one word, for example: python)"
            )
        if len(tag) > TAG_MAX_CHARS or len(tag.encode()) > TAG_MAX_BYTES:
            raise InvalidSubscription(f"a hashtag has at most {TAG_MAX_CHARS} characters")
        return tag
    raise InvalidSubscription(f"the kind must be one of {', '.join(KINDS)}")


def display_name(kind: str, value: str) -> str:
    return f"@{value}" if kind == "handle" else f"#{value}"
