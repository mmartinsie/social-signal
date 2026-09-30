"""Database connection settings shared by every service.

Read from the environment, which the Helm chart fills from each zone's own
Secret. The password is preferably read from a file (DB_PASSWORD_FILE, a
mounted Secret) so it never appears in the process environment.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    name: str
    user: str
    password: str = field(repr=False)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> "DatabaseSettings":
        password_file = environ.get("DB_PASSWORD_FILE")
        if password_file:
            password = Path(password_file).read_text().strip()
        else:
            password = environ["DB_PASSWORD"]
        return cls(
            host=environ["DB_HOST"],
            port=int(environ.get("DB_PORT", "5432")),
            name=environ["DB_NAME"],
            user=environ["DB_USER"],
            password=password,
        )
