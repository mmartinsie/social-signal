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

The scripts also use `curl` and `shasum`, which come preinstalled on macOS
and on most Linux distributions. [uv](https://docs.astral.sh/uv/) (0.12.21)
is only needed for local development: Python dependencies are installed
inside the Docker builds.

Clone the repository into a path **without spaces**, because `make` cannot
handle them.

Machine resources: *TBD*.

## Build

```sh
make build
```

This is the only step that needs internet access to registries and PyPI.
It does two things:

1. **Third-party images:** downloads every one of them, pinned to an exact
   version, into an offline bundle under `dist/images/<arch>/`. That
   includes the k3s system images, which are checksum-verified, and
   PostgreSQL.
2. **Our images:** builds them with Docker from one Dockerfile
   (`docker/python-service.Dockerfile`, Python 3.12 with uv, non-root).
   Each one is tagged with a hash of its content and added to the bundle,
   with the references written to `dist/images/<arch>/app/images.txt`.

The bundle is about 490 MB so far. `make start` then runs everything from
it without pulling anything. Running `make build` again skips whatever is
already downloaded, and an unchanged image keeps its tag.

`make build ARCH=arm64` (or `ARCH=amd64`) prepares the bundle for another
architecture. Third-party images are simply downloaded for it, but building
our own images for a foreign architecture needs QEMU emulation on the build
host.

## Run

```sh
make start
```

Starts a local k3d cluster called `socialsignal` (1 server and 2 agents)
from the offline bundle only; it fails and asks for `make build` if the
bundle is missing. The cluster is configured so it cannot pull images from
any registry. `make start` then:

1. creates the namespaces `ingest`, `data` and `analysis`, with a
   default-deny NetworkPolicy in each;
2. generates random database passwords as Kubernetes Secrets, one per zone,
   so each zone only holds its own;
3. installs two Helm releases: `socialsignal-db` (PostgreSQL, in `data`),
   then `socialsignal` (the application). The application's schema
   migration runs first, as a Helm hook; if it fails, nothing new is rolled
   out.

Running it again is safe: it creates, starts or leaves each piece as needed,
and keeps existing passwords.

The first start takes a few minutes while k3s imports its system images
(about 4.5 minutes on an HDD); later starts are faster.

- UI entry point (Traefik): <http://localhost:8088>. *The application: TBD.*
- Kubernetes API: `127.0.0.1:6445`. Nothing is exposed beyond localhost.
- `make start` does not change your current kubectl context. Use
  `kubectl --context k3d-socialsignal ...`, or switch explicitly with
  `kubectl config use-context k3d-socialsignal`.

## Verify

```sh
make verify-boundary
```

Proves the security boundary against the real NetworkPolicies and database
grants, in about 45 seconds (27 checks). It starts temporary pods that carry
the labels of each component (ingestor, API, worker, LLM), so the same
policies apply to them as to the real pods, plus an "outsider" pod in
`default`. It then checks that:

- the ingestor reaches Bluesky and a public IP, but not the Kubernetes API
  (private ranges are excluded);
- the API and the worker resolve names but cannot connect to the internet;
- the LLM cannot even resolve names;
- PostgreSQL is reachable from the ingestor, the API and the worker, but
  not from the LLM or from the outsider pod;
- each zone, logged in with its own credentials, can do exactly what its
  database role needs and gets `permission denied` for the rest. Every
  database check is rolled back, so it leaves no data behind.

It prints a PASS/FAIL table, deletes the pods, and exits non-zero if any
check fails. *Checks against the LLM: TBD.*

## Stop and clean up

```sh
make stop       # stop the cluster, keeping its state; `make start` resumes it
make clean      # delete the cluster; the image bundle in dist/ is kept
make distclean  # delete the cluster and the image bundle
```

`make clean` keeps `dist/` on purpose: on an isolated host the bundle cannot
be downloaded again.

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
│   ├── api/                 # HTTP API and minimal UI (analysis zone)
│   └── migrations/          # Alembic schema migrations (Helm hook Job, data zone)
├── docker/                  # the Dockerfile shared by every Python service
├── deploy/                  # k3d cluster config, platform manifests, Helm charts
├── scripts/                 # helper scripts called by the Makefile
├── docs/                    # decisions, progress, AI usage log
├── DESIGN.md                # design document
├── BRIEF.md                 # the assignment
└── CLAUDE.md                # instructions for the AI coding agent
```

Inside `deploy/`:

- `k3d/`: the cluster configuration.
- `platform/`: the namespaces and default-deny policies.
- `helm/socialsignal-db/`: PostgreSQL (its own release, installed first).
- `helm/socialsignal/`: the application chart (for now, the per-component
  NetworkPolicies).

Generated by `make build` and not versioned: `dist/images/`, the offline
image bundle. Planned: `llm/` (LLM server image).

## Documentation

- [`DESIGN.md`](DESIGN.md): design, assumptions and open items.
- [`docs/DECISIONS.md`](docs/DECISIONS.md): every decision with its
  alternatives and trade-offs.
- [`docs/PROGRESS.md`](docs/PROGRESS.md): current step and how to resume.
- [`docs/AI_USAGE.md`](docs/AI_USAGE.md): how AI agents were used.
