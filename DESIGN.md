# SocialSignal: design

> Work in progress. Sections marked *TBD* are written as the corresponding
> step is implemented (see [`docs/PROGRESS.md`](docs/PROGRESS.md)).

## 1. Overview

SocialSignal lets analysts subscribe to Bluesky handles and hashtags and see a
summary of the recent sentiment of each subscription, how many posts it covers
and when it was last updated. It runs on Kubernetes, on premises, with a small
local LLM. The system is split into three network zones:

- **ingest:** the only zone allowed to reach the internet; reads Bluesky.
- **data:** PostgreSQL, the only bridge between the other two zones.
- **analysis:** API and UI, summary worker and LLM server; no internet
  access.

## 2. Assumptions

How the ambiguous parts of the brief were interpreted. The options considered
and the trade-offs are in [`docs/DECISIONS.md`](docs/DECISIONS.md#1-interpretation-of-the-brief).

- **A1. Model:** "Gemma 4 A2B" is not a published variant. We use Gemma 4
  E2B, the smallest one: Google's official GGUF, quantised to Q4_0 with
  quantisation-aware training, served on CPU by llama.cpp. The weights are
  baked into the image at build time, never downloaded at runtime. E4B was
  the fallback, and was not needed: E2B labelled 14 of 14 test posts
  correctly, sarcasm included (D22).
- **A2. "Recent":** the last 50 posts from the last 7 days (configurable).
- **A3. Summary:** dominant label (positive / neutral / negative), counts per
  label and one LLM-generated sentence, plus the item count and the last
  update time. If the LLM fails, only the label and counts are shown and the
  previous update time is kept.
  - **A tie is `neutral`**, in any combination of labels.
  - **The update time is when the summary was generated:** it changes only
    when the summary's posts change.
- **A4. Users:** no login; all analysts share one subscription list.
- **A5. "Local network only":** enforced with default-deny NetworkPolicies in
  every namespace. The analysis zone can reach only PostgreSQL, the cluster
  DNS and the local LLM, which is stricter than "the local network".
- **A6. Hashtags:** Bluesky blocks unauthenticated search at times, to
  reduce load. Credentials are optional: an app password in a git-ignored
  `.env` becomes a Secret that only the hashtag ingestor mounts, and search
  then always works. Without it, search runs unauthenticated while Bluesky
  allows it, and a warning says how to add credentials when it does not.
- **A7. Platform:** a local k3d cluster (k3s) stands in for an on-prem
  cluster; PostgreSQL is a single instance.
- **A8. Freshness:** ingestion and summarisation run as periodic batch jobs
  (CronJobs), not in real time. The ingestors run every 5 minutes (handles)
  and 20 (hashtags), and the worker every 5, two minutes after them.
- **A9. Classification:** each post is classified once and the result is
  stored.
- **A10. Priorities:** an end-to-end slice first. If time runs out, the cuts
  are, in order: the LLM sentence, the node-drain demo, hashtags.
- **A11. Tooling:** developed on Linux (WSL2) with LF line endings; the
  Makefile stays portable to macOS.

## 3. Architecture

*Components and flows: TBD.*

**Ingestion (D18, D19).** A CronJob in `ingest` runs every 5 minutes. For
each handle subscription it reads the account's latest 50 items from
Bluesky's public API and keeps only the account's own words: its posts and
its own threads, not reposts and not its replies to other accounts. It
stores them in `posts`, linked to the subscription in `subscription_posts`.
- Writes are keyed on the post's `at://` URI, so a run can be repeated at
  no cost, and they need only `INSERT`.
- Each subscription is stored in its own transaction.
- An account Bluesky does not know gives a warning. A network or database
  error fails the Job, which is then visible in `kubectl get jobs`.

Hashtags use the same image with a different subcommand, as a separate
CronJob that runs every 20 minutes (D20, D21). It searches the latest 50
posts with the tag and applies the same rule: no replies to other
accounts.
- With the optional credentials (A6), it logs in and searches through the
  account's PDS.
- Without them, it searches Bluesky's AppView directly. That works only
  while Bluesky allows unauthenticated search.

**Sentiment model (A1, D22, D23).** A `llm` Deployment in `analysis` runs
llama.cpp's server with Gemma 4 E2B baked into the image.
- The server runs with `--offline`, and its NetworkPolicy gives it no
  egress at all.
- Only the worker can reach it, through the `llm` Service.
- Its output is constrained by a JSON schema to one of three labels.
- On 4 CPU cores a post takes from about 2.5 s (short) to 5-8 s (near
  Bluesky's 300 characters), and it uses 3.5 GiB of memory.

**Summary worker (A3, D24).** A CronJob in `analysis` runs every 5 minutes,
two minutes after the ingestors. For each subscription, oldest summary
first:
1. It classifies with the LLM, once, the posts of the window (the last 50
   of the last 7 days) that have no label yet, and stores each label.
2. When every post of the window has a label, it counts them. The dominant
   label is the most frequent one, and `neutral` on any tie.
3. Only if the posts changed, it asks the LLM for one sentence about the 20
   most recent posts, and stores the summary with `updated_at` = now.

The cost of the LLM follows the new posts, not the schedule: a run with
nothing new takes seconds and makes no LLM call. After 180 s a run starts
no new LLM call, and the next run continues. If the sentence fails, the
summary is stored with its label and counts only, and the sentence is
retried. If the LLM is down, nothing is rewritten, and the analysts keep
seeing the last summary with its date.

**Data model (migration `0001`, D16).** All tables are owned by `migrator`;
the application roles only get what their zone needs:

| Table | Purpose | `ingestor` | `analysis` |
|---|---|---|---|
| `subscriptions` | handle or hashtag, unique per (`kind`, `value`) | SELECT | SELECT, INSERT, DELETE |
| `posts` | one row per Bluesky post, keyed by its `at://` URI (idempotent ingestion) | INSERT | SELECT |
| `subscription_posts` | which subscriptions a post belongs to | INSERT | SELECT |
| `post_sentiments` | the label of each post, classified once (A9) | none | SELECT, INSERT, UPDATE |
| `summaries` | one precomputed summary per subscription (A3) | none | SELECT, INSERT, UPDATE, DELETE |

## 4. Key decisions

Summarised here once implemented; the full record is in
[`docs/DECISIONS.md`](docs/DECISIONS.md).

## 5. Security boundary

**Baseline (platform layer, step 3b).** `make start` creates one namespace
per zone (`ingest`, `data`, `analysis`) and a `default-deny-all`
NetworkPolicy in each one, denying all ingress and all egress, DNS included.
k3s enforces it with its embedded kube-router controller. A test pod in
`analysis` cannot even resolve `public.api.bsky.app`, while the same pod in
`default`, which has no policy, gets HTTP 200. These manifests live outside
the Helm release (D7), so uninstalling the application never removes the
baseline or a namespace.

**Per-component allow rules (Helm chart, step 3c).** On top of the
baseline, each component gets only what it needs, selected by its
`app.kubernetes.io/component` label:

| Component (zone) | Ingress from | Egress to |
|---|---|---|
| API (`analysis`) | Traefik only, port 8000 | PostgreSQL, DNS |
| Worker (`analysis`) | nothing | PostgreSQL, DNS, LLM |
| LLM (`analysis`) | worker only, port 8080 | nothing |
| Ingestor (`ingest`) | nothing | internet on TCP 443 only, excluding private and link-local ranges; PostgreSQL; DNS |
| PostgreSQL (`data`, database chart) | ingestor, API, worker, migration Job (5432) | nothing |
| Migration Job (`data`) | nothing | PostgreSQL, DNS |

DNS egress is allowed only towards the CoreDNS pods, and no IP is
hard-coded. The analysis zone is stricter than "local network only": it can
reach PostgreSQL, the cluster DNS and its own LLM, nothing else. The ingestor
cannot reach the LAN or the Kubernetes API even if it is compromised.

**Proof.** `make verify-boundary` starts a curl pod with each component's
labels, so the same policies apply, and checks the outcome (D12):

```
PASS  ingestor  ingest     https://public.api.bsky.app/xrpc/_health   expected open
PASS  ingestor  ingest     https://1.1.1.1                            expected open
PASS  ingestor  ingest     https://kubernetes.default.svc             expected blocked
PASS  api       analysis   dns public.api.bsky.app                    expected resolves
PASS  api       analysis   https://public.api.bsky.app/xrpc/_health   expected blocked
PASS  api       analysis   https://1.1.1.1                            expected blocked
PASS  worker    analysis   (same as api)
PASS  llm       analysis   dns public.api.bsky.app                    expected no-dns
PASS  llm       analysis   https://1.1.1.1                            expected blocked
PASS  ingestor  ingest     tcp postgres.data.svc:5432                 expected open
PASS  api       analysis   tcp postgres.data.svc:5432                 expected open
PASS  worker    analysis   tcp postgres.data.svc:5432                 expected open
PASS  llm       analysis   tcp postgres.data.svc:5432                 expected blocked
PASS  outsider  default    tcp postgres.data.svc:5432                 expected blocked
PASS  worker    analysis   tcp llm.analysis.svc:8080                  expected open
PASS  api       analysis   tcp llm.analysis.svc:8080                  expected blocked
PASS  ingestor  ingest     tcp llm.analysis.svc:8080                  expected blocked
PASS  outsider  default    tcp llm.analysis.svc:8080                  expected blocked
```

The outsider pod sits outside the three zones, and its own egress is open.
Its connections are blocked by the database's and the LLM's own ingress
rules, so both ends of every connection are enforced. The API is in the
same zone as the LLM and still cannot reach it.

**Least privilege in the database (D1, D13).**
- Three login roles:
  - `migrator` owns the database and is the only one with DDL;
  - `ingestor` and `analysis` get `CONNECT` plus the per-table grants in
    §3.
- None of them is superuser or can create roles or databases.
- Their passwords are random and generated on the cluster by `make start`,
  never by Helm, the repository or the bundle. Each zone only holds its own
  (`ingest` has only the ingestor's).
- Every network client must authenticate with SCRAM-SHA-256.

**Bluesky credentials (A6, D21).** The optional app password lives in a
git-ignored `.env`, which never reaches an image. `make start` turns it
into a Secret that exists only in `ingest`.
- It is created with `kubectl create`, not `apply`, which would copy it in
  clear text into an annotation.
- Only the hashtag ingestor mounts it, as files. The handle ingestor never
  sees it, and neither does the analysis zone.
- It appears in no log and no Helm release (tested).

**Proof, second layer (D17).**
- `make verify-boundary` also starts a `psql` pod in each zone, with that
  zone's labels and only that zone's Secret. It logs in over the network
  and tries what the role may and may not do.
- Every check runs inside a transaction that is rolled back.
- *denied* only counts if PostgreSQL answers `permission denied`.

```
PASS  db-ingestor ingest     sql read subscriptions                           expected allowed
PASS  db-ingestor ingest     sql insert a post twice (idempotent)             expected allowed
PASS  db-ingestor ingest     sql read summaries                               expected denied
PASS  db-ingestor ingest     sql write post_sentiments                        expected denied
PASS  db-ingestor ingest     sql delete subscriptions                         expected denied
PASS  db-ingestor ingest     sql create table                                 expected denied
PASS  db-analysis analysis   sql read posts and links                         expected allowed
PASS  db-analysis analysis   sql subscribe, then write its summary twice      expected allowed
PASS  db-analysis analysis   sql insert posts                                 expected denied
PASS  db-analysis analysis   sql create table                                 expected denied
PASS  lifecycle   data       sql subscribe, ingest, summarise, unsubscribe    expected allowed
```

The last line runs the whole data flow in one rolled-back transaction, each
step as the role that will perform it (`SET LOCAL ROLE`):
1. the API subscribes;
2. the ingestor stores and links a post;
3. the worker classifies it and summarises;
4. the API unsubscribes, and the cascade removes the link and the summary.

The flow works with exactly the grants in §3 and nothing more, because
foreign-key checks and cascades run with the table owner's privileges.
Granting the ingestor one extra privilege makes the run fail (tested).

**Untrusted text reaches the LLM (D24).** Posts come from the internet, and
the worker passes them to the LLM, so a post could try to steer it (prompt
injection). What limits the damage:
- The LLM has no tools and no network: it can only return text.
- For each post, its output is constrained by a JSON schema to one of three
  labels.
- The summary sentence is free text, but it is only displayed, as text. The
  prompt declares the posts as data, and puts the deterministic counts next
  to them, so a steered sentence would contradict the numbers shown beside
  it.

At worst, one post could distort its own label or its subscription's
sentence.

## 6. High availability

**PostgreSQL: one pod, on purpose (D14).**
- The database is a single-replica StatefulSet with a persistent volume.
  Today any restart or upgrade is an outage. Recreating the pod took about
  6 s, with its data intact; meanwhile the API cannot read and the CronJobs
  retry on their next run.
- Adding replicas to this StatefulSet would create independent databases,
  not replicas.
- Scaling means CloudNativePG: a primary plus streaming replicas, automatic
  failover, and a Service that always points to the primary. The
  applications would not change, since they connect by Service name.

**LLM: one pod, on purpose (D23).**
- Only the batch worker uses it, and while it is down the summaries are
  still served, with their last update time (A3).
- It runs as 1 replica with `strategy: Recreate`. A rolling update would
  run two pods of about 4 GiB side by side, which a small node cannot
  afford.
- Its image is on every node, so if its node goes down it is rescheduled
  elsewhere. Classification then pauses for about 40 s while the model
  loads.

**Summary worker: a CronJob (D24).** A run on a failed node is simply
replaced by the next one, on another node, 5 minutes later. Labels are
stored as they are produced, so no work is lost. While the worker or the
LLM is down, the API keeps serving the last summaries.

*API replicas, probes, PDB and node drain: TBD (step 10).*

## 7. Continuous updates

**Separate releases for data and applications (D2).** PostgreSQL is its own
Helm release (`socialsignal-db`), installed before the application. The
application's schema migration runs as a `pre-install`/`pre-upgrade` hook,
which Helm executes before creating resources, so the database must already
exist. Upgrading or uninstalling the application never touches the data, and
upgrading PostgreSQL does not touch the application.

**Upgrading PostgreSQL (documented, not implemented; D14).**
- *Minor* (18.6 → 18.7): the on-disk format is the same. Change
  `POSTGRES_IMAGE`, then run `make build` and `make start`. Only the database
  pod restarts, with a short outage.
- *Major* (18 → 19): the data directory must be converted, with one of:
  - `pg_upgrade --link` in a Job with both versions' binaries (minutes of
    outage);
  - dump and restore into a new StatefulSet (offline blue/green);
  - logical replication (online blue/green, near-zero outage, most complex).

With CloudNativePG, minor upgrades become a rolling update plus a
switchover, with near-zero outage.

**Images tagged by content (D15).** Each image's tag is a hash of its
content, so it changes if and only if the image changes: a rebuild without
changes is a no-op, while any change produces a new tag, a new spec and a
rollout. This matters because the cluster cannot pull and uses
`IfNotPresent`: a reused tag would keep running old code.

**Migrations gate every release (D16).** Alembic runs as a
`pre-install/pre-upgrade` hook Job, before any new application pod. If it
fails, Helm aborts the upgrade and the previous version keeps running; this
was tested by forcing a failure. Rollbacks do not undo migrations, so every
migration must be backward compatible (expand/contract).

*Application rolling updates: TBD (step 10).*

## 8. Delivery to isolated environments

`make build` is the only step that downloads images. It saves every
third-party image, pinned to an exact version, as a tarball under
`dist/images/<arch>/`, including the k3s system images, which are
checksum-verified. `make start` runs the cluster from that bundle alone, so
the deployment host needs no registry access. Its only outbound traffic is
the ingestor reading Bluesky. The bundle can be built on a connected machine
and carried to the target. The cluster is also configured so it *cannot*
pull: every registry is mirrored to an unresolvable address and k3s'
fallback to the real registry is disabled (D9). A connected laptop therefore
behaves like an isolated site, and an image missing from the bundle fails
visibly instead of being downloaded. The LLM's weights travel the same way,
inside the LLM image, pinned and checksum-verified at build time (D22). On a site with its own registry (e.g. Harbor), the
same tarballs would be pushed there instead. See
[D4](docs/DECISIONS.md#d4-getting-images-into-the-cluster-offline-image-bundle-step-3a).

*The rest is TBD.*

## 9. How AI agents were used

*TBD (step 12).* The running log is in [`docs/AI_USAGE.md`](docs/AI_USAGE.md).

## 10. Time spent

*TBD (step 12).*

## 11. Open items

- **Highly available PostgreSQL:** replace the single instance with the
  CloudNativePG operator: replication, failover, and near-zero-outage minor
  upgrades (D14).
- **PostgreSQL major upgrades:** automate one of the documented paths
  (`pg_upgrade` Job, dump/restore or logical replication).
- **Secrets at rest:** enable k3s `--secrets-encryption`, one line in
  `deploy/k3d/cluster.yaml`, applied when the cluster is created. Today
  Secrets are only base64-encoded in the datastore.
- **Encryption in transit to PostgreSQL:** the official image runs with
  `ssl = off`, so connections from the zones travel unencrypted inside the
  cluster network. Enable TLS on the server, with a certificate from an
  internal CA (e.g. cert-manager), and require `sslmode=verify-full` in the
  clients.
- **External secret manager:** Vault, External Secrets Operator, Sealed
  Secrets or SOPS, for rotation and audit of the database and Bluesky
  credentials (D13).
- **Users and authentication:** login (e.g. OIDC at the ingress) and
  per-analyst subscription lists.
- **DNS tunnelling:** the analysis zone may query the cluster DNS, which
  forwards to upstream resolvers. That is a theoretical exfiltration channel;
  close it by restricting CoreDNS forwarding for that zone or with an
  internal-only resolver.
- **Bundle integrity:** images are pinned by tag and only the k3s tarball is
  checksum-verified. Pin every image by digest and ship a signed manifest of
  the bundle, including build provenance for our own images, whose
  attestations are disabled to keep tags deterministic (D15).
- **Readable release versions:** combine a human version (e.g. `0.2.0`)
  with the content digest for our images (D15).
- **Follow accounts by DID:** subscriptions store the handle, which is
  resolved on every call. A renamed account then answers "Profile not
  found". Resolve the handle once, store the account's DID, which never
  changes, and fetch by DID (D18).
- **Replies to other accounts, with context:** they are excluded today
  because, without the post they answer, the LLM cannot interpret them
  (often sarcasm). Fetch the parent post and classify the pair (D18).
- **Reuse the Bluesky session:** the hashtag ingestor logs in on every run,
  and Bluesky allows 300 logins per day per account, which bounds how often
  it can run. Keeping the refresh token between runs would lift that limit,
  but needs writable storage in `ingest` or a long-running pod (D20).
- **OAuth instead of an app password:** an app password can act as the
  account, although the ingestor only reads. Bluesky's OAuth allows
  narrower permissions (D20).
- **A real evaluation of the classifier:** the model was only checked on
  15 hand-labelled posts (14 correct), and a sarcastic post reworded
  without an explicit complaint was misclassified (D22). Label a few
  hundred real posts, measure accuracy per class, and use that set to
  compare prompts and models (E2B against E4B), and to catch regressions
  when either changes.
- **Event-driven summaries:** the ingestor could signal new posts through
  PostgreSQL `NOTIFY`, and an always-running worker `LISTEN` for them. It
  keeps the boundary, since zones only meet in `data`, and would cut a few
  minutes of delay, at the cost of reconnection handling and a sweep for
  missed notifications (D24).
- **Show when the worker last ran:** `updated_at` is when a summary was
  generated, so a quiet handle shows an old date even when everything
  works. Recording each successful run would let the UI tell "no new
  posts" from "the worker is not running" (D24).
- **Build progress for the LLM image:** the build prints nothing for about
  6 minutes while Docker compresses the 3.35 GB layer, which looks like a
  hang. Show BuildKit's progress for that image.
