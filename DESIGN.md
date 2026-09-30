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

*TBD (step 3).*

## 6. High availability

*TBD (step 10).*

## 7. Continuous updates

*TBD (step 10).*

## 8. Delivery to isolated environments

*TBD.*

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
