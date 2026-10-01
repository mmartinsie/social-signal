# Progress

_Last updated: 2026-10-01 (step 9)._

## Current step

**Step 9: the API and the minimal UI (D25).** Done, in one go at the
author's request, with every recommended decision:
- `api` Deployment (2 replicas), Service and Traefik Ingress in
  `analysis`: the UI at <http://localhost:8088>, plus a small JSON API;
- a page rendered on the server, with no JavaScript and no external
  assets; every state is explained (pending, being analysed, no recent
  posts, no sentence);
- probes that never touch the database; writes from another origin
  refused; Jinja2 escapes the LLM's sentence;
- 52 new unit tests (148 in total);
- end to end in the cluster: subscribed `@AtProto.com` through the form,
  saw it go from pending to a summary in about 3 minutes, then
  unsubscribed;
- with PostgreSQL scaled to 0, the page said so with a 503, the pods stayed
  ready, and the API recovered on its own;
- what must stay untouched was checked: NetworkPolicies, the database
  chart, the migration, the platform, the other services, the LLM image
  and `.env` are unchanged; `verify-boundary` 31/31 and `llm-smoke` 3/3.

Next: **step 10**, high availability and zero-downtime updates:
PodDisruptionBudget, rolling update with `maxUnavailable: 0`, spreading
the API over nodes, graceful shutdown, and a demo of an update and of a
node drain without downtime.

**State of the cluster:**
- The UI shows `@bsky.app` (1 post, positive) and `#python` (50 posts,
  neutral), with sentences. `@atproto.com` was subscribed and then
  unsubscribed in the test; its posts and labels stay in the database.
- The API runs 2 replicas, on different nodes; the LLM runs on one node,
  and its image is present on all three.
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
| 9 | API and minimal UI, behind Traefik | Done (2026-10-01) |
| 10 | High availability and zero-downtime updates | Pending |
| 11 | `make build` and `make start` from a clean clone | Pending |
| 12 | Final documentation and zip review | Pending |

## Follow-ups

- Review the *Options / Why / Trade-off* write-ups drafted in
  [`DECISIONS.md`](DECISIONS.md).
- Step 10: the API's probes check only the process (D25). For a rolling
  update without errors, add a graceful shutdown: on SIGTERM, `/readyz`
  should fail first (or a `preStop` sleep) so Traefik stops sending
  requests before uvicorn stops.
- Step 10: the two API replicas landed on different nodes by chance; add a
  topology spread constraint or anti-affinity.
- Step 10: the LLM image is on every node, so the LLM can be rescheduled
  when its node is drained. Expect about 40 s without classification while
  the model loads (D23). The worker then fails one run and recovers on
  the next (D24).
- Step 10: the `local-path` volume pins PostgreSQL to one node. For the
  drain demo, drain a node that does *not* host `postgres-0`, or explain the
  outage (D14). While PostgreSQL is down, the UI answers 503 and says so
  (D25).
- Step 10 or 12: add the API's ingress checks to `make verify-boundary`
  (only Traefik reaches it; tested by hand in step 9).

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
| 2026-09-30 / 10-01 | 5a-9 | *TBD* | Session 3 (WSL, new conversation) |
