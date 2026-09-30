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

Machine resources, measured on the development machine (WSL2 with 10 GB of
memory, an HDD):

- **Memory:** Docker needs at least 8 GB. The LLM pod alone uses about
  3.5 GiB; the whole cluster ran with 6 GiB of the 10 GB still available.
- **Disk:** about 60 GB free:
  - the bundle, 3.8 GB, plus the model, 3.4 GB;
  - Docker's copies of our images, about 9 GB;
  - the three k3d nodes, about 26 GB, because each one holds the LLM image;
  - Docker's build cache, which `docker builder prune` can reclaim.
- **CPU:** the LLM uses up to 4 cores, at about 2.5 s per post.

## Build

```sh
make build
```

This is the only step that needs internet access to registries, PyPI and
Hugging Face. It does three things:

1. **Third-party images:** downloads every one of them, pinned to an exact
   version, into an offline bundle under `dist/images/<arch>/`. That
   includes the k3s system images, which are checksum-verified, and
   PostgreSQL.
2. **The LLM weights:** downloads Google's Gemma 4 E2B (QAT Q4_0 GGUF,
   3.35 GB) into `dist/models/`, pinned to a repository revision and
   checked against its sha256. An interrupted download resumes on the next
   run.
3. **Our images:** builds them with Docker, each tagged with a hash of its
   content and added to the bundle, with the references written to
   `dist/images/<arch>/app/images.txt`:
   - `migrations` and `ingestor`, from one Dockerfile
     (`docker/python-service.Dockerfile`, Python 3.12 with uv, non-root);
   - `llm`: llama.cpp's server with the model baked in
     (`docker/llm.Dockerfile`, non-root), so nothing is downloaded at
     runtime.

The bundle is about 3.8 GB, 3.5 GB of it the LLM image. The first build
takes about 10 minutes on an HDD: the download, plus compressing and saving
the LLM image. `make start` then runs everything from the bundle without
pulling anything. Running `make build` again skips whatever is already
downloaded, and an unchanged image keeps its tag.

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
3. turns the optional Bluesky credentials in `.env` into a Secret in
   `ingest` (see below), or removes that Secret if `.env` has none;
4. installs two Helm releases: `socialsignal-db` (PostgreSQL, in `data`),
   then `socialsignal` (the application). The application's schema
   migration runs first, as a Helm hook; if it fails, nothing new is rolled
   out. The application release includes two **ingestor** CronJobs in
   `ingest`:
   - `ingestor-handles` reads the subscribed Bluesky accounts every 5
     minutes;
   - `ingestor-hashtags` reads the subscribed hashtags every 20 minutes.

Running it again is safe: it creates, starts or leaves each piece as needed,
and keeps existing passwords.

### Optional: Bluesky credentials for hashtags

Hashtag search works without credentials only while Bluesky allows it: it
blocks unauthenticated search at times, to reduce load. Handles never need
credentials. To make hashtag search always work:

1. In Bluesky, create an **app password** (Settings > Privacy and security >
   App passwords). Never use your account's own password.
2. Create `.env` from the template and fill it in with an editor:
   ```sh
   cp .env.example .env && chmod 600 .env
   ```
3. Run `make start`.

`.env` is git-ignored and never copied into an image. Only the hashtag
ingestor mounts the resulting Secret. With credentials, each hashtag run
logs in once, and Bluesky allows 300 logins per day per account: the
20-minute schedule uses 72.

The first start takes a few minutes while k3s imports its system images
(about 4.5 minutes on an HDD). Importing the 3.5 GB LLM image into the
three nodes adds about 10 minutes on an HDD, but only when that image
changes; later starts are faster.

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
grants, in about 45 seconds (31 checks). It starts temporary pods that carry
the labels of each component (ingestor, API, worker, LLM), so the same
policies apply to them as to the real pods, plus an "outsider" pod in
`default`. It then checks that:

- the ingestor reaches Bluesky and a public IP, but not the Kubernetes API
  (private ranges are excluded);
- the API and the worker resolve names but cannot connect to the internet;
- the LLM cannot even resolve names;
- PostgreSQL is reachable from the ingestor, the API and the worker, but
  not from the LLM or from the outsider pod;
- the LLM is reachable only from the worker: not from the API, the
  ingestor or the outsider pod;
- each zone, logged in with its own credentials, can do exactly what its
  database role needs and gets `permission denied` for the rest. Every
  database check is rolled back, so it leaves no data behind.

It prints a PASS/FAIL table, deletes the pods, and exits non-zero if any
check fails.

### Check the LLM

```sh
make llm-smoke
```

From a pod with the worker's identity, classifies three unambiguous posts
with the offline LLM and checks the labels (a few seconds per post on CPU).

### See the ingestor working

Until the UI exists, create a subscription with `psql`, as the `analysis`
role that the API will use:

```sh
kubectl --context k3d-socialsignal exec -n data postgres-0 -- \
  psql -U postgres -d socialsignal \
  -c "SET ROLE analysis; INSERT INTO subscriptions (kind, value) VALUES ('handle', 'bsky.app'), ('hashtag', 'python') ON CONFLICT DO NOTHING;"
```

Handles are stored without `@` and hashtags without `#`, both lower-case.
Then run an ingestor now, instead of waiting for its schedule, and read its
log. `ingestor-hashtags` works the same way:

```sh
kubectl --context k3d-socialsignal -n ingest create job handles-now --from=cronjob/ingestor-handles
kubectl --context k3d-socialsignal -n ingest wait --for=condition=complete job/handles-now
kubectl --context k3d-socialsignal -n ingest logs job/handles-now
```

The first run reports the posts it stored. A second run reports
`0 new posts`, because storing a post again is a no-op. Without
credentials, the hashtag log says whether it searched unauthenticated, or
whether Bluesky is blocking that.

### Unit tests (development)

```sh
uv run pytest
```

### Evaluate the LLM (development)

`tools/llm_eval.py` runs the LLM image with no network and checks it on a
small hand-labelled set (sarcasm and Spanish included), reporting the
accuracy and the latency per post. How to run it is in its docstring. It is
a smoke check, not a benchmark.

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
├── tests/                   # unit tests (outside the images' build context)
├── tools/                   # development tools, e.g. the LLM evaluation
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
- `helm/socialsignal/`: the application chart: the per-component
  NetworkPolicies, the migration Job, the two ingestor CronJobs and the LLM.

Generated by `make build` and not versioned: `dist/images/`, the offline
image bundle. Planned: `llm/` (LLM server image).

## Documentation

- [`DESIGN.md`](DESIGN.md): design, assumptions and open items.
- [`docs/DECISIONS.md`](docs/DECISIONS.md): every decision with its
  alternatives and trade-offs.
- [`docs/PROGRESS.md`](docs/PROGRESS.md): current step and how to resume.
- [`docs/AI_USAGE.md`](docs/AI_USAGE.md): how AI agents were used.
