# SocialSignal

On-premises sentiment analysis of Bluesky handles and hashtags, running on
Kubernetes with a small local LLM.

**In short:**

```sh
make build             # once, with internet access (up to 30 minutes)
make start             # about 23 minutes the first time, 1 minute later on
# then open http://localhost:8088 in a browser
```

`make verify-boundary`, `make demo-update` and `make demo-drain` then prove
the security boundary and the updates without downtime. The design, and why
each choice was made, are in [`DESIGN.md`](DESIGN.md).

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
  3.5 GiB; with the whole system running, about 5 GB of the 10 GB stayed
  available.
- **Disk:** about 60 GB free:
  - the bundle, about 4 GB, plus the model, 3.4 GB;
  - Docker's copies of our images, about 9 GB;
  - the three k3d nodes, about 26 GB, because each one holds the LLM image;
  - Docker's build cache, which `docker builder prune` can reclaim.
- **CPU:** the LLM uses up to 4 cores, at 2.5 to 8 s per post depending on
  its length.

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
   - `migrations`, `ingestor`, `worker` and `api`, from one Dockerfile
     (`docker/python-service.Dockerfile`, Python 3.12 with uv, non-root);
   - `llm`: llama.cpp's server with the model baked in
     (`docker/llm.Dockerfile`, non-root), so nothing is downloaded at
     runtime.

The bundle is about 4 GB, 3.5 GB of it the LLM image. From a clean clone
on the development machine (HDD), `make build` took 12.5 minutes: 1.5 for
the third-party images, 4.5 to download the model, 1.5 for our Python
images and 5 to build and save the LLM image. Docker's build cache was warm
there. **On a machine that never built these images, allow up to 30
minutes** with an HDD and a connection of 50 Mbit/s or more (an estimate
from the measured parts, not measured end to end). It downloads about
4.2 GB, 3.35 GB of them the model, so a slower connection takes longer;
an SSD makes compressing and saving the LLM image much faster.

`make start` then runs everything from the bundle without pulling anything.
Running `make build` again skips whatever is already downloaded, and an
unchanged image keeps its tag.

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
   default-deny NetworkPolicy in each, and runs two pods of Traefik and of
   CoreDNS (k3s runs one of each), so the UI survives losing a node;
2. generates random database passwords as Kubernetes Secrets, one per zone,
   so each zone only holds its own;
3. turns the optional Bluesky credentials in `.env` into a Secret in
   `ingest` (see below), or removes that Secret if `.env` has none;
4. installs two Helm releases: `socialsignal-db` (PostgreSQL, in `data`),
   then `socialsignal` (the application). The application's schema
   migration runs first, as a Helm hook; if it fails, nothing new is rolled
   out. The application release includes the **API and UI** (2 replicas,
   behind Traefik), the **LLM**, and three CronJobs:
   - `ingestor-handles`, in `ingest`, reads the subscribed Bluesky
     accounts every 5 minutes (:00, :05…);
   - `ingestor-hashtags`, in `ingest`, reads the subscribed hashtags every
     20 minutes (:00, :20, :40);
   - `worker`, in `analysis`, updates the summaries every 5 minutes, two
     minutes after the ingestors (:02, :07…). It classifies new posts with
     the LLM and rewrites a summary only when its posts change.

Running it again is safe: it creates, starts or leaves each piece as needed,
and keeps existing passwords.

**How long it takes**, measured from a clean clone on the development
machine (HDD):
- **The first `make start`: about 23 minutes.** 16.5 of them import the
  images into the three nodes: our 3.5 GB LLM image, while k3s imports its
  own system images at the same time. Then about 3 minutes for the system
  components and 2 for the two Helm releases, the LLM loading included.
- **Later starts: about 1 minute**, as long as no image changed; a changed
  LLM image adds about 10 minutes.
- On an SSD every import is much faster.

- **The UI:** <http://localhost:8088>, through Traefik, bound to
  localhost.
- Kubernetes API: `127.0.0.1:6445`. Nothing is exposed beyond localhost.
- `make start` does not change your current kubectl context. Use
  `kubectl --context k3d-socialsignal ...`, or switch explicitly with
  `kubectl config use-context k3d-socialsignal`.

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
ingestor mounts the resulting Secret. To change or revoke the password, edit
`.env` (or empty it) and run `make start` again: the Secret is replaced (or
deleted) within a minute. With credentials, each hashtag run logs in once,
and Bluesky allows 300 logins per day per account: the 20-minute schedule
uses 72.

## Use it

Open <http://localhost:8088> and subscribe to a Bluesky account (for
example `bsky.app`) or a hashtag (for example `python`). The `@` and `#`
are optional. Each subscription then goes through these states:

1. **Waiting for the first posts:** until the next ingestor run, at most
   5 minutes for an account and 20 for a hashtag. If it stays here, check
   that the account or hashtag exists: the analysis zone has no internet,
   so the UI cannot check it for you.
2. **Being analysed:** the worker runs every 5 minutes. On CPU a post takes
   2.5 to 8 s depending on its length, so a new subscription with 50 posts
   can take two runs.
3. **The summary:** the dominant label (`neutral` on a tie), the count per
   label, the number of posts it covers (the last 50 of the last 7 days),
   one sentence written by the LLM, and when it was last updated. The
   sentence may be missing if the LLM did not answer; the label and counts
   are still up to date.

Reload the page to see new results. The same through the JSON API:

```sh
curl -s http://localhost:8088/api/subscriptions
curl -s -H 'Content-Type: application/json' -d '{"kind": "hashtag", "value": "python"}' \
  http://localhost:8088/api/subscriptions
curl -s -X DELETE http://localhost:8088/api/subscriptions/<id>
```

### Skip the wait (optional)

Run an ingestor and then the worker now, instead of waiting for their
schedules, and read their logs. `ingestor-hashtags` works like
`ingestor-handles`:

```sh
kubectl --context k3d-socialsignal -n ingest create job handles-now --from=cronjob/ingestor-handles
kubectl --context k3d-socialsignal -n ingest wait --for=condition=complete job/handles-now
kubectl --context k3d-socialsignal -n ingest logs job/handles-now

kubectl --context k3d-socialsignal -n analysis create job worker-now --from=cronjob/worker
kubectl --context k3d-socialsignal -n analysis wait --for=condition=complete --timeout=5m job/worker-now
kubectl --context k3d-socialsignal -n analysis logs job/worker-now
```

- **The ingestor's log** reports the posts it stored; a second run reports
  `0 new posts`, because storing a post again is a no-op. Without
  credentials, the hashtag log says whether it searched unauthenticated, or
  whether Bluesky is blocking that.
- **The worker's log** reports what it classified and summarised. A run
  with nothing new ends in seconds and logs `unchanged`. While the LLM is
  starting, the run fails with `the LLM … is not ready: nothing done`, and
  the summaries are kept.

## Verify

```sh
make verify-boundary
```

Proves the security boundary against the real NetworkPolicies and database
grants, in about a minute (35 checks). It starts temporary pods that carry
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
- the API is reachable only through Traefik: from your machine, through
  `http://localhost:8088`, but not from the ingestor, the worker or the
  outsider pod;
- each zone, logged in with its own credentials, can do exactly what its
  database role needs and gets `permission denied` for the rest. Every
  database check is rolled back, so it leaves no data behind.

It prints a PASS/FAIL table, deletes the pods, and exits non-zero if any
check fails.

### Updates and node drains without downtime

```sh
make demo-update   # replace every API pod, as a new image does (about 1 minute)
make demo-drain    # drain a node running an API pod, then uncordon it (about 1 minute)
```

Each one sends requests to the JSON API through Traefik, from your machine,
several times per second, while it disrupts the cluster, and keeps going
until the old pods are gone. It then prints how many requests failed and
exits non-zero if any did. Expected: `No request failed: zero downtime.`

- The drain picks a node that runs an API pod but not PostgreSQL, which is a
  single instance; moving it would be an outage (see `DESIGN.md`). It
  always uncordons the node, also if interrupted.
- If the LLM runs on the drained node, it moves to another one and reloads
  in about 40 s. A worker run stopped by the drain shows as `Failed`; the
  next one catches up.

### Check the LLM

```sh
make llm-smoke
```

From a pod with the worker's identity, classifies three unambiguous posts
with the offline LLM and checks the labels (a few seconds per post on CPU).

## Development

### Unit tests

```sh
uv run pytest
```

### Evaluate the LLM

`tools/llm_eval.py` runs the LLM image with no network and checks it on a
small hand-labelled set (sarcasm and Spanish included), reporting the
accuracy and the latency per post. It runs in the worker image and uses the
worker's own LLM client, so it measures exactly the worker's prompts. How to
run it is in its docstring. It is a smoke check, not a benchmark.

## Stop and clean up

```sh
make stop       # pause the CronJobs and stop the cluster, keeping its state
make clean      # delete the cluster; the image bundle in dist/ is kept
make distclean  # delete the cluster and the image bundle
```

`make start` after `make stop` resumes the cluster and the CronJobs, usually
in about a minute. Docker may give the nodes new IPs on restart. k3s then
restarts on those nodes for a minute or two, and k3d may print a `FATA`
line about its load balancer. `make start` notes it, waits for the nodes
(up to 10 minutes) and carries on (D28).

On WSL2, Linux keeps the files it read cached after `make stop`, and Windows
still counts that memory as the VM's. `make stop` prints the command that
gives it back.

`make clean` keeps `dist/` on purpose: on an isolated host the bundle cannot
be downloaded again.

## Repository layout

```
.
├── Makefile                 # build, start, stop, clean, verify-boundary, demos
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
├── docs/                    # requirements, decisions, progress, AI usage log
├── DESIGN.md                # design document
└── CLAUDE.md                # instructions for the AI coding agent
```

Inside `deploy/`:

- `k3d/`: the cluster configuration.
- `platform/`: the namespaces, the default-deny policies, and two Traefik
  and CoreDNS pods with their PodDisruptionBudgets.
- `helm/socialsignal-db/`: PostgreSQL (its own release, installed first).
- `helm/socialsignal/`: the application chart: the per-component
  NetworkPolicies, the migration Job, the two ingestor CronJobs, the LLM,
  the summary worker's CronJob, and the API with its Service and Ingress.

Generated by `make build` and not versioned: `dist/images/`, the offline
image bundle, and `dist/models/`, the LLM weights.

## Documentation

- [`DESIGN.md`](DESIGN.md): architecture, assumptions, key decisions, the
  security boundary, high availability, updates, delivery to isolated
  sites, how AI agents were used, time spent and open items.
- [`docs/DECISIONS.md`](docs/DECISIONS.md): every decision with its
  alternatives, trade-offs and what was verified, plus the table of
  verified external facts.
- [`docs/AI_USAGE.md`](docs/AI_USAGE.md): how AI agents were used, step by
  step.
- [`docs/PROGRESS.md`](docs/PROGRESS.md): the steps, their state and how to
  resume work.
- [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md): what the system had to
  do. [`CLAUDE.md`](CLAUDE.md): the working rules given to the AI agent.
