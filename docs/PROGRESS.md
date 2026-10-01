# Progress

_Last updated: 2026-10-01 (step 11)._

## Current step

**Step 11: `make build` and `make start` from a clean clone (D27).** Done:
- a `git clone` into `~/social-signal-clean`, with no `dist/` and no `.env`;
  nothing had to be fixed;
- `make build` 12.5 minutes, the first `make start` 23 minutes (16.5 of
  them importing images), a second `make start` 1 minute;
- `verify-boundary` 31/31, `llm-smoke` 3/3, the README's flow end to end
  (both subscriptions summarised), `demo-update` 393/393 and `demo-drain`
  358/358;
- with the author's `.env` copied in, the hashtag ingestor logged in;
- **a security incident caused by the agent:** a failed `kubectl`
  template printed the Bluesky Secret's values into the agent's session.
  The author revoked the app password and set a new one in `.env`;
  `make start` replaced the Secret, and the login works.

Next: **step 12**, the final documentation (README, DESIGN with open
items, how AI agents were used, the time spent) and a review of the zip.

**State of the cluster:**
- **It now runs from the clone** (`~/social-signal-clean`): k3s re-imports its
  system images from that directory's `dist/` whenever a node starts, so
  keep it until the cluster is recreated from `~/social-signal` (about 23 minutes)
  or the project ends. `make` commands work from either directory: the
  cluster's name and context are the same, and so are the image tags.
- New data: `@bsky.app` (1 post, positive) and `#python` (47 posts,
  neutral). The earlier data was lost with the old cluster, as agreed.
- With the new password in both `.env` files, `ingestor-hashtags` logs in
  every 20 minutes while the cluster runs.

## Steps

| # | Step | Status |
|---|---|---|
| 0 | Read the brief; requirements, ambiguities and plan | Done (2026-09-30) |
| 1 | Prerequisites | Done (2026-09-30) |
| 2 | Repository skeleton | Done (2026-09-30) |
| 3a | Offline image bundle (`make build` downloads all third-party images) | Done (2026-09-30) |
| 3b | k3d cluster from the bundle, namespaces and default-deny (`make start/stop/clean/distclean`) | Done (2026-09-30) |
| 3c | Per-component allow rules (Helm chart) and `make verify-boundary` | Done (2026-09-30) |
| 4a | PostgreSQL in its own release, login roles, per-zone credentials, network checks | Done (2026-09-30) |
| 4b | Python image pipeline, Alembic migrations (Helm hook), schema and grants | Done (2026-09-30) |
| 4c | Database privilege checks in `make verify-boundary` | Done (2026-09-30) |
| 5a | Handle ingestor code, unit tests, real call to Bluesky | Done (2026-09-30) |
| 5b | Ingestor image and CronJob, end to end into PostgreSQL | Done (2026-09-30) |
| 6a | Hashtag ingestor code, unit tests, real calls to Bluesky | Done (2026-09-30) |
| 6b | Credentials Secret and hashtag CronJob, end to end | Done (2026-09-30) |
| 7a | LLM image (model baked in), local evaluation | Done (2026-10-01) |
| 7b | LLM in the cluster, boundary checks, smoke test | Done (2026-10-01) |
| 8 | Summary worker: code and tests, image and CronJob, LLM sentence | Done (2026-10-01) |
| 9 | API and minimal UI, behind Traefik | Done (2026-10-01) |
| 10 | High availability and zero-downtime updates, with drain and update demos | Done (2026-10-01) |
| 11 | `make build` and `make start` from a clean clone | Done (2026-10-01) |
| 12 | Final documentation and zip review | Pending |

## Follow-ups

- Review the *Options / Why / Trade-off* write-ups drafted in
  [`DECISIONS.md`](DECISIONS.md).
- Step 12: add the API's ingress checks to `make verify-boundary` (only
  Traefik reaches it; tested by hand in step 9), or leave it as an open
  item.
- Step 12: fill in the time log below, and DESIGN's sections on AI use and
  time spent.
- After the project: delete `~/social-signal-clean` only together with the
  cluster (`make clean`), or after recreating it from `~/social-signal`.

## How to resume

- Work inside WSL2 (Ubuntu 24.04); the repository is at `~/social-signal`. Docker
  Engine runs inside WSL, not Docker Desktop.
- WSL shuts the distribution down when it is idle (about 15 s with no WSL
  processes), which stops Docker and the k3d cluster. `make start` brings the
  cluster back (about 2 minutes). To avoid it, set `instanceIdleTimeout=-1`
  under `[general]` in `%UserProfile%\.wslconfig`.
- kubectl: `kubectl --context k3d-socialsignal ...`. On this machine the
  context is already the current one, because the kubeconfig had none
  before (D8).
- From Windows PowerShell 5.1, embedded double quotes break
  `wsl -e bash -lc "..."`; use Git Bash with `MSYS_NO_PATHCONV=1` instead.
- `uv sync --all-packages` recreates the development virtualenv, including
  pytest; `uv run pytest` runs the unit tests.

## Time log

Filled in by the author; it feeds the time report in `DESIGN.md`.

| Date | Steps | Time | Notes |
|---|---|---|---|
| 2026-09-30 | 0-1 | *TBD* | Session 1 (Windows) |
| 2026-09-30 | 2-4c | *TBD* | Session 2 (WSL) |
| 2026-09-30 / 10-01 | 5a-11 | *TBD* | Session 3 (WSL, new conversation) |
