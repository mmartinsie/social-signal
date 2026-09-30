# SocialSignal

On-premises sentiment analysis of Bluesky handles and hashtags, running on
Kubernetes with a small local LLM.

> Work in progress: see [`docs/PROGRESS.md`](docs/PROGRESS.md) for the current
> state.

## Prerequisites

Tested with:

| Tool | Version tested |
|---|---|
| Docker Engine | 29.8.1 |
| k3d | 5.9.0 |
| kubectl | 1.36.5 |
| Helm | 4.3.0 (the chart uses `apiVersion: v2`, readable by Helm 3) |
| make | GNU make 4.3 (the Makefile avoids features newer than make 3.81, the macOS default) |

[uv](https://docs.astral.sh/uv/) (0.12.21) is only needed for local
development: Python dependencies are installed inside the Docker builds.

Machine resources: *TBD*.

## Build

```sh
make build
```

*TBD.*

## Run

```sh
make start
```

*TBD.*

## Verify

```sh
make verify-boundary
```

*TBD.*

## Stop and clean up

```sh
make stop
make clean
```

*TBD.*

## Repository layout

```
.
├── Makefile                 # build / start / stop / clean / verify-boundary
├── pyproject.toml, uv.lock  # uv workspace (Python 3.12)
├── packages/
│   └── common/              # shared settings and database access
├── services/
│   ├── ingestor/            # Bluesky -> PostgreSQL (ingest zone)
│   ├── worker/              # sentiment classification and summaries (analysis zone)
│   └── api/                 # HTTP API and minimal UI (analysis zone)
├── docs/                    # decisions, progress, AI usage log
├── DESIGN.md                # design document
├── BRIEF.md                 # the assignment
└── CLAUDE.md                # instructions for the AI coding agent
```

Planned: `deploy/` (k3d configuration and Helm chart), `llm/` (LLM server
image) and `scripts/`.

## Documentation

- [`DESIGN.md`](DESIGN.md): design, assumptions and open items.
- [`docs/DECISIONS.md`](docs/DECISIONS.md): every decision with its
  alternatives and trade-offs.
- [`docs/PROGRESS.md`](docs/PROGRESS.md): current step and how to resume.
- [`docs/AI_USAGE.md`](docs/AI_USAGE.md): how AI agents were used.
