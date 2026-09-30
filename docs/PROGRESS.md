# Progress

_Last updated: 2026-09-30 (step 2)._

## Current step

**Step 3: k3d cluster, namespaces, default-deny NetworkPolicies, test pods and
`make verify-boundary`.** Being proposed; not started.

## Steps

| # | Step | Status |
|---|---|---|
| 0 | Read the brief; requirements, ambiguities and plan | Done (2026-09-30) |
| 1 | Prerequisites | Done (2026-09-30) |
| 2 | Repository skeleton | Done (2026-09-30) |
| 3 | k3d cluster, namespaces, NetworkPolicies, `make verify-boundary` | Pending |
| 4 | PostgreSQL: schema, migrations and roles | Pending |
| 5 | Handle ingestor, end to end into PostgreSQL | Pending |
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
- Step 3: choose between the k3d local registry and `k3d image import` (D4).
- Step 4: decide where the Alembic migrations live.
- Step 6: decide how hashtag credentials are provided (A6).
- Step 8: decide the tie-break rule for the dominant label (A3).

## How to resume

- Work inside WSL2 (Ubuntu 24.04); the repository is at `~/social-signal`. Docker
  Engine runs inside WSL, not Docker Desktop.
- WSL shuts the distribution down when it is idle (about 15 s with no WSL
  processes). That stops Docker and, from step 3 on, the k3d cluster;
  `k3d cluster start` brings it back. To avoid it, set
  `instanceIdleTimeout=-1` under `[general]` in `%UserProfile%\.wslconfig`.
- From Windows PowerShell 5.1, embedded double quotes break
  `wsl -e bash -lc "..."`; use Git Bash with `MSYS_NO_PATHCONV=1` instead.
- `uv sync --all-packages` recreates the development virtualenv.

## Time log

Filled in by the author; it feeds the time report in `DESIGN.md`.

| Date | Steps | Time | Notes |
|---|---|---|---|
| 2026-09-30 | 0-1 | *TBD* | Session 1 (Windows) |
| 2026-09-30 | 2 | *TBD* | Session 2 (WSL) |
