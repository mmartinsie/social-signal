# Progress

_Last updated: 2026-10-21 (step 14)._

## Current step

**Step 14, preparing the public repository:** the requirements are now in
[`REQUIREMENTS.md`](REQUIREMENTS.md), written in the project's own words,
and the documents refer to "the requirements". Next: rewrite the git
history so no earlier commit holds the original requirements document,
then publish the result as a new public repository.

**Step 13, after closing (D28):** `make stop` followed by `make start`
failed when Docker gave the nodes new IPs. Now `make start` waits for the
nodes instead of failing; `make stop` pauses the CronJobs and `make start`
resumes them once everything is ready; `db-secrets.sh` can no longer dump a
Secret if its template fails. Tested by forcing new IPs and a failing k3d.

**Steps 0-12 were done by 2026-10-01.** Step 12, the final documentation:
- `DESIGN.md` complete: an architecture diagram and the flow, a table of
  the key decisions, delivery to isolated sites, how AI agents were used,
  the time spent (about 6 hours) and the open items grouped by theme;
- `make verify-boundary` also checks the API's ingress (35 checks), and a
  mutation test proved the new checks can fail (D12);
- the author reviewed the 17 decisions drafted in step 2; A3, A5, A10, D2
  and D3 were updated;
- the README starts with a short summary, and its figures were refreshed.

**The project is complete.** The zip of the repository (`socialsignal.zip`)
is made from a fresh clone of the final commit, so it holds the repository with its
git history and nothing git-ignored (no `.env`, no personal notes, no
`dist/`):
1. `git clone --no-local` of the final commit;
2. in the clone, remove the remote and the reflog, which hold local paths;
3. zip it with directory entries included (git needs some empty ones, such
   as `.git/refs/heads`) and with the files' permissions (the scripts are
   executable);
4. check it by extracting it elsewhere: `git status` clean, `git fsck`
   without errors, and the same tree as the final commit.

**State of the cluster:** it runs from `~/social-signal-clean` (step 11), with
`@bsky.app` and `#python` summarised. Keep that directory until the cluster
is deleted (`make clean`) or recreated from `~/social-signal`.

## Steps

| # | Step | Status |
|---|---|---|
| 0 | Read the requirements; summary, ambiguities and plan | Done (2026-09-30) |
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
| 12 | Final documentation, API ingress checks, decisions reviewed, zip | Done (2026-10-01) |
| 13 | `make stop` / `make start` survive new node IPs; CronJobs paused while stopped | Done (2026-10-03) |
| 14 | Public repository: requirements in our own words, history rewritten | In progress |

## Follow-ups

- Delete `~/social-signal-clean` only together with the cluster
  (`make clean`), or after recreating it from `~/social-signal`.

## How to resume

- Work inside WSL2 (Ubuntu 24.04); the repository is at `~/social-signal`.
  Docker Engine runs inside WSL, not Docker Desktop.
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
| 2026-09-30 | 0-1 | | Session 1 (Windows) |
| 2026-09-30 | 2-4c | | Session 2 (WSL) |
| 2026-09-30 / 10-01 | 5a-12 | | Session 3 (WSL, new conversation) |
| **Total** | 0-12 | **about 6 hours** | The author's active time, not split per session; the gaps between commits are breaks |
