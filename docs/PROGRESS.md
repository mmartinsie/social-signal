# Progress

_Last updated: 2026-09-30 (step 5a)._

## Current step

**Step 5a: handle ingestor code, unit tests and a real call to Bluesky.**
Done: 25 tests pass. The code has not run against the database yet (D18).

Next: **step 5b**:
- the ingestor image and its CronJob in the Helm chart;
- `make build` and `make start`;
- end to end in the cluster: a demo subscription, a manual Job run twice
  (the second stores nothing new), and `make verify-boundary`.

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
| 5b | Ingestor image and CronJob, end to end into PostgreSQL | Pending |
| 6 | Hashtag ingestor with authentication | Pending |
| 7 | Offline LLM server and classification smoke test | Pending |
| 8 | Summary worker | Pending |
| 9 | API and minimal UI | Pending |
| 10 | High availability and zero-downtime updates | Pending |
| 11 | `make build` and `make start` from a clean clone | Pending |
| 12 | Final documentation and zip review | Pending |

## Follow-ups

- Review the *Options / Why / Trade-off* write-ups drafted in
  [`DECISIONS.md`](DECISIONS.md).
- Step 5b: until the API exists (step 9), the demo subscription is created
  with `psql` as `analysis` (`SET ROLE analysis` in `postgres-0`).
- Step 5b: `packages/common` now depends on psycopg and has `connect()`.
  Every image copies `packages/`, so the migrations image gets a new tag
  and its hook re-runs as a no-op. That is expected (D15).
- Steps 5b and 9: pods must carry `app.kubernetes.io/component`, and
  Services must also select `app.kubernetes.io/instance`, so that the
  `verify-boundary` test pods never receive traffic (D12).
- Step 6: decide how hashtag credentials are provided (A6).
- Step 7: `k3d image import` copies each image into all 3 nodes, and imports
  are slow on this HDD. Measure it with the multi-GB LLM image and consider
  importing it only where the LLM runs. Add the LLM checks to
  `verify-boundary`: the worker reaches it, the API does not.
- Step 8: decide the tie-break rule for the dominant label (A3).
- Step 10: the `local-path` volume pins PostgreSQL to one node. For the
  drain demo, drain a node that does *not* host `postgres-0`, or explain the
  outage (D14).

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
| 2026-09-30 | 5a | *TBD* | Session 3 (WSL, new conversation) |
