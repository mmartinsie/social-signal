"""The analysts' API and minimal UI (D25), in the analysis zone.

  GET  /                              the page: subscribe, unsubscribe, summaries
  POST /subscriptions                 form: subscribe, then back to the page
  POST /subscriptions/{id}/delete     form: unsubscribe, then back to the page
  GET  /api/subscriptions             the same data as JSON
  POST /api/subscriptions             {"kind", "value"}: 201 created, 200 existing
  DELETE /api/subscriptions/{id}      204, or 404
  GET  /healthz, /readyz              liveness and readiness: the process only

The pages are rendered on the server, with no JavaScript and no external
assets, so they work in an isolated network. Jinja2 escapes everything,
including the LLM's sentence, which is written from posts off the internet.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from socialsignal_api.store import Store, Subscription, Unavailable
from socialsignal_api.subscriptions import InvalidSubscription, display_name, normalise

TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass(frozen=True)
class Window:
    """What "recent" means (A2), shown on the page; the worker's values."""

    max_posts: int = 50
    days: int = 7


class SubscriptionIn(BaseModel):
    kind: Literal["handle", "hashtag"]
    value: str


def create_app(store: Store, window: Window = Window()) -> FastAPI:
    # No /docs or /redoc: Swagger UI loads its JavaScript from a CDN, which
    # an isolated network cannot reach.
    app = FastAPI(title="SocialSignal", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def same_origin_writes(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # There is no login (A4). Without this check, any web page the
        # analyst opens could make the browser post to this UI on the local
        # network (cross-site request forgery). Browsers send Origin on
        # every cross-site POST; clients without one (curl) are allowed.
        origin = request.headers.get("origin")
        if request.method in UNSAFE_METHODS and origin is not None:
            if urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "cross-origin request refused"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(Unavailable)
    async def database_unavailable(request: Request, error: Unavailable) -> Response:
        message = "The database is not reachable right now. Try again in a minute."
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": message}, status_code=503)
        return page(request, [], error=message, status_code=503)

    def page(
        request: Request,
        subscriptions: list[Subscription],
        *,
        error: str | None = None,
        form: dict[str, str] | None = None,
        status_code: int = 200,
    ) -> Response:
        now = datetime.now(UTC)
        return TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "rows": [row(s, now) for s in subscriptions],
                "window": window,
                "error": error,
                "form": form or {"kind": "handle", "value": ""},
            },
            status_code=status_code,
        )

    @app.get("/")
    def index(request: Request) -> Response:
        return page(request, store.subscriptions())

    @app.post("/subscriptions")
    def subscribe_form(
        request: Request, kind: Annotated[str, Form()], value: Annotated[str, Form()]
    ) -> Response:
        try:
            store.subscribe(kind, normalise(kind, value))
        except InvalidSubscription as error:
            form = {"kind": kind, "value": value}
            return page(
                request, store.subscriptions(), error=str(error), form=form, status_code=400
            )
        # Post/redirect/get: reloading the page does not post again.
        return RedirectResponse("/", status_code=303)

    @app.post("/subscriptions/{subscription_id}/delete")
    def unsubscribe_form(subscription_id: int) -> Response:
        store.unsubscribe(subscription_id)
        return RedirectResponse("/", status_code=303)

    @app.get("/api/subscriptions")
    def list_subscriptions() -> list[dict]:
        return [as_json(s) for s in store.subscriptions()]

    @app.post("/api/subscriptions")
    def subscribe(body: SubscriptionIn, response: Response) -> dict:
        try:
            value = normalise(body.kind, body.value)
        except InvalidSubscription as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        subscription_id, created = store.subscribe(body.kind, value)
        response.status_code = 201 if created else 200
        return {"id": subscription_id, "kind": body.kind, "value": value, "created": created}

    @app.delete("/api/subscriptions/{subscription_id}", status_code=204)
    def unsubscribe(subscription_id: int) -> Response:
        if not store.unsubscribe(subscription_id):
            raise HTTPException(status_code=404, detail="no such subscription")
        return Response(status_code=204)

    # Neither probe touches the database: if PostgreSQL is down, every
    # replica would turn unready at once and the analysts would get a bare
    # 503 from Traefik instead of a page that says what is wrong.
    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict:
        return {"status": "ready"}

    return app


def row(subscription: Subscription, now: datetime) -> dict:
    """What the page shows for one subscription."""
    summary = subscription.summary
    if not subscription.has_posts:
        # Not fetched yet, or Bluesky does not know it: the API cannot tell,
        # it has no internet access.
        state = "pending"
    elif summary is None:
        state = "analysing"
    elif summary.item_count == 0:
        state = "empty"
    else:
        state = "ready"
    return {
        "id": subscription.id,
        "name": display_name(subscription.kind, subscription.value),
        "kind": subscription.kind,
        "state": state,
        "summary": summary,
        "updated": ago(summary.updated_at, now) if summary else None,
        "updated_iso": summary.updated_at.astimezone(UTC).isoformat(timespec="seconds")
        if summary
        else None,
    }


def ago(moment: datetime, now: datetime) -> str:
    seconds = max(0, int((now - moment).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} h ago"
    days = seconds // 86400
    return f"{days} day{'s' if days > 1 else ''} ago"


def as_json(subscription: Subscription) -> dict:
    summary = subscription.summary
    return {
        "id": subscription.id,
        "kind": subscription.kind,
        "value": subscription.value,
        "created_at": subscription.created_at.isoformat(),
        "has_posts": subscription.has_posts,
        "summary": None
        if summary is None
        else {
            "dominant_label": summary.dominant_label,
            "counts": {
                "positive": summary.positive,
                "neutral": summary.neutral,
                "negative": summary.negative,
            },
            "item_count": summary.item_count,
            "text": summary.text,
            "updated_at": summary.updated_at.isoformat(),
        },
    }
