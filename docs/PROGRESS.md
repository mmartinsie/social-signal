# Progress

_Last updated: 2026-10-01 (step 10)._

## Current step

**Step 10: high availability and updates without downtime (D26).** Done:
- **API:** rolling update (`maxSurge 1`, `maxUnavailable 0`), one pod per
  node, a PDB, a 10 s `preStop` pause plus uvicorn's graceful shutdown,
  and a 1 s DNS retry;
- **platform:** two Traefik pods (a k3s `HelmChartConfig`, with a pause
  too) and two CoreDNS pods, each with a PDB;
- **demos:** `make demo-update` and `make demo-drain`, under load from the
  host, failing on any failed request;
- **measured:** the first drain failed 86 of 356 requests. The agent found
  two causes, Traefik stopping at once and CoreDNS stopping at once, and
  fixed them. Then: a rolling update 359 of 359, a `make start` 901 of 901,
  and a drain of the node with an API, a Traefik and a CoreDNS pod and the
  LLM, 237 of 237;
- `verify-boundary` 31/31, `llm-smoke` 3/3.

Next: **step 11**, `make build` and `make start` from a clean clone.

**State of the cluster:**
- The UI shows `@bsky.app` and `#python`, with sentences.
- After the drains, the pods are spread differently than before, and two
  worker Jobs show `Failed` (stopped by drains); the next runs succeeded.
- The demo subscriptions stay until they are no longer needed (author's
  decision). With the author's `.env`, `ingestor-hashtags` logs in to
  Bluesky every 20 minutes while the cluster runs (72 of the account's 300
  daily logins). `make stop` stops it.
- The machine's clock jumped from about 01:00 to 07:00 UTC during this
  step (probably a suspend); the logs' times reflect it.

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
| 11 | `make build` and `make start` from a clean clone | Pending |
| 12 | Final documentation and zip review | Pending |

## Follow-ups

- Review the *Options / Why / Trade-off* write-ups drafted in
  [`DECISIONS.md`](DECISIONS.md).
- Step 11: from a clean clone, `make build` then `make start`. Check that
  the platform's high availability comes up on a new cluster (the Traefik
  `HelmChartConfig` and the CoreDNS scaling in `cluster-up.sh`), and run
  both demos there.
- Step 11 or 12: add the API's ingress checks to `make verify-boundary`
  (only Traefik reaches it; tested by hand in step 9).
- Step 12: the README's measured times (first start, imports) predate the
  platform changes; re-measure them in step 11.

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
| 2026-09-30 / 10-01 | 5a-10 | *TBD* | Session 3 (WSL, new conversation) |
