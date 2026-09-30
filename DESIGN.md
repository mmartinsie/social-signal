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
  E2B, the smallest one, quantised (GGUF Q4) and served on CPU by llama.cpp.
  The weights are baked into the image at build time, never downloaded at
  runtime. E4B is the fallback.
- **A2. "Recent":** the last 50 posts from the last 7 days (configurable).
- **A3. Summary:** dominant label (positive / neutral / negative), counts per
  label and one LLM-generated sentence, plus the item count and the last
  update time. If the LLM fails, only the label and counts are shown and the
  previous update time is kept.
- **A4. Users:** no login; all analysts share one subscription list.
- **A5. "Local network only":** enforced with default-deny NetworkPolicies in
  every namespace. The analysis zone can reach only PostgreSQL, the cluster
  DNS and the local LLM, which is stricter than "the local network".
- **A6. Hashtags:** Bluesky search requires an authenticated account. How the
  credentials are provided is decided in step 6.
- **A7. Platform:** a local k3d cluster (k3s) stands in for an on-prem
  cluster; PostgreSQL is a single instance.
- **A8. Freshness:** ingestion and summarisation run as periodic batch jobs
  (CronJobs), not in real time.
- **A9. Classification:** each post is classified once and the result is
  stored.
- **A10. Priorities:** an end-to-end slice first. If time runs out, the cuts
  are, in order: the LLM sentence, the node-drain demo, hashtags.
- **A11. Tooling:** developed on Linux (WSL2) with LF line endings; the
  Makefile stays portable to macOS.

## 3. Architecture

*TBD.*

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
| PostgreSQL (`data`) | ingestor, API, worker, migration Job (5432) | nothing |
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
```

*Checks against PostgreSQL (step 4) and the LLM (step 7): TBD.*

## 6. High availability

*TBD (step 10).*

## 7. Continuous updates

*TBD (step 10).*

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
visibly instead of being downloaded. On a site with its own registry (e.g. Harbor), the
same tarballs would be pushed there instead. See
[D4](docs/DECISIONS.md#d4-getting-images-into-the-cluster-offline-image-bundle-step-3a).

*The rest is TBD.*

## 9. How AI agents were used

*TBD (step 12).* The running log is in [`docs/AI_USAGE.md`](docs/AI_USAGE.md).

## 10. Time spent

*TBD (step 12).*

## 11. Open items

- **Highly available PostgreSQL:** replace the single instance with the
  CloudNativePG operator (replication and failover).
- **Users and authentication:** login (e.g. OIDC at the ingress) and
  per-analyst subscription lists.
- **DNS tunnelling:** the analysis zone may query the cluster DNS, which
  forwards to upstream resolvers. That is a theoretical exfiltration channel;
  close it by restricting CoreDNS forwarding for that zone or with an
  internal-only resolver.
- **Bundle integrity:** images are pinned by tag and only the k3s tarball is
  checksum-verified. Pin every image by digest and ship a signed manifest of
  the bundle.
