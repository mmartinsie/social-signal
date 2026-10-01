# Progress

_Last updated: 2026-10-01 (step 8)._

## Current step

**Step 8: the summary worker (D24).** Done, in one go at the author's
request (8a code and tests, 8b image and CronJob, 8c the LLM sentence):
- `worker` CronJob in `analysis`, every 5 minutes at :02, :07…;
- it classifies each post of the window once, and rewrites a summary only
  when its posts change; ties are `neutral`;
- 43 new unit tests (96 in total); the SQL was checked as `analysis` in a
  rolled-back transaction;
- in the cluster, the first run found everything unclassified: it used up
  its 180 s budget after 34 posts, and the next run finished `#python`
  (17 posts in 77 s, the sentence in 49 s);
- with the LLM scaled to 0, the run failed with "not ready: nothing done"
  and both summaries were kept; once it was back, the next run caught up
  on its own;
- a run with nothing new logs `unchanged` and leaves `updated_at` alone;
- `verify-boundary` 31/31.

Next: **step 9**, the API and the minimal UI. It reads `summaries` and
manages `subscriptions` as `analysis`.

**State of the cluster:**
- Summaries for `@bsky.app` (1 post, positive) and `#python` (50 posts,
  neutral), with sentences.
- The LLM runs on one node, and its image is present on all three.
- The demo subscriptions stay until they are no longer needed (author's
  decision). With the author's `.env`, `ingestor-hashtags` logs in to
  Bluesky every 20 minutes while the cluster runs (72 of the account's 300
  daily logins). `make stop` stops it.

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
| 9 | API and minimal UI | Pending |
| 10 | High availability and zero-downtime updates | Pending |
| 11 | `make build` and `make start` from a clean clone | Pending |
| 12 | Final documentation and zip review | Pending |

## Follow-ups

- Review the *Options / Why / Trade-off* write-ups drafted in
  [`DECISIONS.md`](DECISIONS.md).
- Until the API exists (step 9), subscriptions are created with `psql` as
  `analysis` (`SET ROLE analysis` in `postgres-0`; see the README).
- Step 9: pods must carry `app.kubernetes.io/component: api`, and its
  Service must also select `app.kubernetes.io/instance`, so that the
  `verify-boundary` test pods never receive traffic (D12).
- Step 9: use the Helm helpers for the database environment and the
  security contexts (D21), with the `credentials.analysis` Secret, as the
  worker does.
- Step 9: show each summary's `updated_at`, the counts and the item count;
  a summary may have no sentence (degraded mode) or no label (no recent
  posts). A subscription without a row in `summaries` is still pending.
- Step 9: display the LLM's sentence as text, never as HTML: it is written
  from untrusted posts (D24).
- Step 10: the LLM image is on every node, so the LLM can be rescheduled
  when its node is drained. Expect about 40 s without classification while
  the model loads (D23). The worker then fails one run and recovers on
  the next (D24).
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
| 2026-09-30 / 10-01 | 5a-8 | *TBD* | Session 3 (WSL, new conversation) |
