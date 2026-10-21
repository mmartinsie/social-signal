# Requirements

What socialsignal was built to do. How the open points were interpreted is
recorded in [`DECISIONS.md`](DECISIONS.md#1-interpretation-of-the-requirements)
(A1-A11).

## What analysts need

Analysts follow a curated set of public Bluesky sources. They must be able
to:

1. subscribe to, and unsubscribe from, Bluesky **handles** and **hashtags**;
2. see a **summary of the recent sentiment** of each subscription;
3. see **how many posts** that summary covers;
4. see **when it was last updated**.

## Constraints

- **Sentiment model:** a small LLM running locally. The Gemma 4 family was
  suggested, under the name "Gemma 4 A2B", which is not a published variant
  (A1). No cloud LLM APIs.
- **Security boundary:**
  - only the ingestion may reach the internet, to read Bluesky;
  - the analysis side may only reach the analysts' local network;
  - the boundary must be enforced by the infrastructure, not only by the
    code.
- **Deployment:** on premises, on Kubernetes. The focus is packaging,
  deployment and network setup:
  - the system must be **highly available** to the analysts;
  - it must accept **continuous software updates**.
- **Stack:** Python 3.12 or later, with uv.

## Deliverables

- A working system, in a repository.
- A `README.md` with instructions to build and run it.
- A `Makefile` with `make build` (dependencies and build) and `make start`
  (start the system).
- A design document with the key decisions.

## Process

- **Timebox:** about one evening. Whatever is unfinished is recorded as an
  open item.
- **AI agents are welcome**, but the author must be able to answer for the
  design, its trade-offs, the security boundary, high availability and the
  update strategy.
