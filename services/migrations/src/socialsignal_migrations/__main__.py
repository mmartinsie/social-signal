"""Entry point of the migration Job: `python -m socialsignal_migrations`.

Alembic is configured in code rather than with an alembic.ini, so the image
needs no config file and the connection comes only from the environment
(DatabaseSettings). Upgrading to "head" is idempotent: a second run with no
new revisions does nothing.
"""

import logging
from importlib.resources import files

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL

from socialsignal_common.db import DatabaseSettings


def database_url(settings: DatabaseSettings) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=settings.user,
        password=settings.password,
        host=settings.host,
        port=settings.port,
        database=settings.name,
    )


def main() -> None:
    # Without an alembic.ini there is no logging config: show Alembic's
    # progress ("Running upgrade ...") in the Job's logs.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config = Config()
    config.set_main_option("script_location", str(files("socialsignal_migrations") / "alembic"))
    # Passed as an attribute, not as a main option: config options go through
    # ConfigParser interpolation, which would mangle a '%' in a password.
    config.attributes["url"] = database_url(DatabaseSettings.from_env())
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
