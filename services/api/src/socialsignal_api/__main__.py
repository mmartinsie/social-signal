"""Entry point of the API Deployment:

    python -m socialsignal_api

Serves the UI and the JSON API with uvicorn on API_PORT (8000). Database
settings come from the environment, like every other service; the window
("recent", A2) is the worker's, so the page describes what it shows.
"""

import logging
import os

import uvicorn

from socialsignal_api.app import Window, create_app
from socialsignal_api.store import Store
from socialsignal_common.db import DatabaseSettings, connect


class NoProbes(logging.Filter):
    """Keep the kubelet's probes, every few seconds, out of the access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return "/healthz" not in message and "/readyz" not in message


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("uvicorn.access").addFilter(NoProbes())
    database = DatabaseSettings.from_env()
    window = Window(
        max_posts=int(os.environ.get("SUMMARY_MAX_POSTS", "50")),
        days=int(os.environ.get("SUMMARY_WINDOW_DAYS", "7")),
    )
    store = Store(lambda: connect(database, application_name="socialsignal-api"))
    uvicorn.run(
        create_app(store, window),
        host="0.0.0.0",
        port=int(os.environ.get("API_PORT", "8000")),
        # Behind Traefik, the only client the NetworkPolicy lets in.
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_config=None,
    )


if __name__ == "__main__":
    main()
