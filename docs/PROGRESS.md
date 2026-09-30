# Progress

_Last updated: 2026-10-01 (step 7b)._

## Current step

**Step 7b: the LLM in the cluster (D23).** Done:
- `llm` Deployment (1 replica, `Recreate`) and Service in `analysis`;
- it loads the model in about 40 s and uses 3.5 GiB of memory;
- `verify-boundary` passes 31/31: only the worker reaches the LLM;
- `make llm-smoke` passes 3/3, at about 2.5 s per post.

The first `make start` with the LLM image took about 12 minutes on this
HDD, 9 of them importing it into the three nodes.

Next: **step 8**, the summary worker. Decide first:
- the tie-break rule (A3);
- how often to write the LLM sentence, which takes 98 s over 50 posts
  (D22).

**State of the cluster:**
- The LLM runs on one node, and its image is present on all three.
- The demo subscriptions `handle bsky.app` and `hashtag python` stay, so
  the worker (step 8) has posts to classify: 92 posts at the end of step 6b
  (42 and 50).
- With the author's `.env`, `ingestor-hashtags` logs in to Bluesky every
  20 minutes while the cluster runs (72 of the account's 300 daily logins).
  `make stop` stops it.

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
| 8 | Summary worker | Pending |
| 9 | API and minimal UI | Pending |
| 10 | High availability and zero-downtime updates | Pending |
| 11 | `make build` and `make start` from a clean clone | Pending |
| 12 | Final documentation and zip review | Pending |

## Follow-ups

- Review the *Options / Why / Trade-off* write-ups drafted in
  [`DECISIONS.md`](DECISIONS.md).
- Until the API exists (step 9), subscriptions are created with `psql` as
  `analysis` (`SET ROLE analysis` in `postgres-0`; see the README).
- Steps 8 and 9: pods must carry `app.kubernetes.io/component`, and Services
  must also select `app.kubernetes.io/instance`, so that the
  `verify-boundary` test pods never receive traffic (D12).
- Steps 8 and 9: use the Helm helpers from step 6b for the database
  environment and the security contexts (D21).
- Step 8: the worker reaches the LLM at `http://llm.analysis.svc:8080`, with
  the prompt and `response_format` of `tools/llm_eval.py`.
- Step 10: the LLM image is on every node, so the LLM can be rescheduled
  when its node is drained. Expect about 40 s without classification while
  the model loads (D23).
- Step 8: decide the tie-break rule for the dominant label (A3).
- Step 8: one summary sentence over 50 posts took 98 s on CPU (D22). Decide
  how often to write it: for example only when a subscription has new
  posts, over fewer or shorter posts, or not at all. A10 already makes it
  the first cut.
- Step 8: the worker must use `response_format` in OpenAI's form; llama.cpp
  v0.5.0 ignores the form its README documents (D22).
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
| 2026-09-30 / 10-01 | 5a-7b | *TBD* | Session 3 (WSL, new conversation) |
