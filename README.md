# SocialSignal

**How I build software with an AI coding agent, shown on a real system.**

SocialSignal is a working system: an on-premises sentiment analysis of
Bluesky handles and hashtags, on Kubernetes, with a small local LLM. But
the reason this repository is public is how it was built. I wrote it with
an AI coding agent, Claude Code (Claude Opus 5.5), and every step, every
decision and every mistake along the way is recorded here: what I
delegated, what I decided, and how I checked the result.

## Why this repository exists

The requirements come from an old technical exercise: a system for analysts
who follow Bluesky sources, with a hard security boundary, high
availability and continuous updates, built with a small local LLM, in
about one evening. The original text is not included:
[`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) restates it in my own words.

I keep this record because I think how you work with an AI agent matters
as much as what it produces. Anyone can get code out of an agent; what I
want to show is the method that makes the result something I understand,
can defend and would put into production.

## How I work with the agent

### Rules first

Before any code, I wrote the agent's working rules. They are versioned in
[`CLAUDE.md`](CLAUDE.md), and the agent followed them for the whole
project:

- **Small steps,** each one reviewable and testable in a few minutes.
- **Explain, then wait.** Before each step the agent says what it will do,
  why, which files it will touch and which commands it will run. Then it
  stops until I say OK. It explains in Spanish; every file in the
  repository is in English.
- **Approval for anything that changes something.** Reading is free;
  installing, building, changing the cluster or committing needs my OK.
- **Verify, don't assume.** A decision that depends on an external fact
  (an API, a model, a tool version) is checked against the documentation,
  the source code or a real test, and the source is recorded.
- **Every decision written down,** with the alternatives and the
  trade-offs.
- **After each step:** what changed, how I can check it myself with an
  exact command, and what could go wrong.
- **When something fails,** no improvised big fixes: explain the error,
  propose one or two options, and wait.

### I decide; the agent proposes, builds and verifies

The agent laid out the options with a recommendation, wrote the code, the
tests and the documents, ran the checks and measured. I decided the scope
and every product and risk trade-off. Some of my decisions:

- any tie between sentiment labels counts as `neutral`, and a summary's
  "last updated" means when it was generated (A3);
- Bluesky credentials are optional: without them, hashtag search runs
  unauthenticated while Bluesky allows it (A6);
- hashtags are polled every 20 minutes, not 5: each run logs in, and
  Bluesky allows 300 logins a day (D21);
- the name of the project, over the agent's proposal.

### Verify, don't trust

- **87 external facts,** each with its source, in the table at the end of
  [`docs/DECISIONS.md`](docs/DECISIONS.md#5-verified-facts). One of them
  was wrong: it came from secondary sources, a real call disproved it, and
  it stays in the table, struck through, with the correction.
- **Checks that are made to fail.** To prove `make verify-boundary` can
  catch a broken rule, a temporary policy opened the API to everyone, and
  exactly the expected check failed. To prove the cluster recovers after a
  restart, a placeholder container forced new node IPs, and a fake `k3d`
  failed on purpose (D28).
- **Measured, not estimated:** zero failed requests during a rolling update
  and during a node drain, under load (D26).

### When the agent got it wrong

The mistakes are recorded, not hidden, with how each one was caught:

- **A wrong fact** about Bluesky's search authentication, corrected when it
  was tested.
- **An estimate at half the real value:** the time to classify a post,
  found by measuring.
- **A demo that stopped measuring too early,** before the old pods were
  gone. Found, fixed and measured again.
- **A secret in the agent's session.** A failed `kubectl` template printed
  a Secret's values. The agent stopped and said so, I rotated the password,
  and Secrets are now inspected only with `kubectl describe` (D27). Later,
  a script that used the same mechanism was hardened (D28).
- **A first fix that failed its own test.** Helm 4 refused it because of
  server-side apply. The agent explained why and redid it (D28).

### In numbers

| | |
|---|---|
| My active time | about 6 hours for the first twelve steps, over two days |
| Decisions recorded | 47, each with alternatives and trade-offs |
| Verified external facts | 87 |
| Unit tests | 148, no database, network or model needed |
| Security boundary checks | 35, against the real cluster |

## Where to look

| To see | Read |
|---|---|
| The instructions I gave the agent | [`CLAUDE.md`](CLAUDE.md) |
| What the system had to do | [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) |
| Every decision, with alternatives, trade-offs and verified facts | [`docs/DECISIONS.md`](docs/DECISIONS.md) |
| The collaboration step by step: what I decided, what the agent did, what went wrong | [`docs/AI_USAGE.md`](docs/AI_USAGE.md) |
| The resulting design | [`DESIGN.md`](DESIGN.md) |
| The steps and their state | [`docs/PROGRESS.md`](docs/PROGRESS.md) |
| The story in commits | `git log --reverse --oneline` |

The history was rewritten before publishing: the text of the original
exercise was removed from every commit, and the commits use GitHub's
no-reply address instead of my email. The steps, their order and the code
are the same (step 14 in [`docs/AI_USAGE.md`](docs/AI_USAGE.md)).

## The project

Analysts subscribe to Bluesky handles and hashtags and see, for each one,
the recent sentiment (positive, neutral or negative), the count per label,
how many posts it covers, a one-sentence summary and when it was last
updated.

```
 Analysts' browsers ──► Traefik ×2
                           │ only Traefik reaches the API
 ┌─ analysis: no internet ─▼───────────────────────────────┐
 │ API ×2 (UI and JSON)    worker (CronJob) ──► LLM        │
 │                         Gemma 4 E2B on llama.cpp, CPU   │
 └──────────────────────────┬──────────────────────────────┘
                            │ SQL, one role per zone
 ┌─ data ───────────────────▼──────────────────────────────┐
 │ PostgreSQL: the only bridge between the zones           │
 └──────────────────────────▲──────────────────────────────┘
                            │ SQL
 ┌─ ingest: HTTPS out only ─┴──────────────────────────────┐
 │ ingestors (CronJobs) ──► Bluesky's public API           │
 └─────────────────────────────────────────────────────────┘
```

- **Security boundary:** default-deny NetworkPolicies in every zone, one
  allow rule per component and one database role per zone. Only the
  ingestion reaches the internet.
- **High availability and updates:** two replicas of the API, of Traefik and
  of CoreDNS, PodDisruptionBudgets, and rolling updates with no downtime.
- **Offline delivery:** `make build` bundles every image and the model;
  `make start` never pulls anything, and the cluster cannot.

### Quick start

```sh
make build    # once, with internet access (up to 30 minutes)
make start    # about 23 minutes the first time, 1 minute later on
# then open http://localhost:8088 in a browser
```

It needs Docker, k3d, kubectl, Helm and make, about 8 GB of memory for
Docker and 60 GB of disk. The prerequisites, building, running, using,
verifying and the zero-downtime demos are in
[`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md). How it works, and why,
is in [`DESIGN.md`](DESIGN.md).
