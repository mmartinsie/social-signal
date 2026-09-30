# CLAUDE.md — socialsignal

## Context

- I'm Manuel, a backend engineer (Python, Docker, Kubernetes, Helm, Linux). I'm building socialsignal, an on-premises system that summarises the sentiment of Bluesky handles and hashtags with a small local LLM.
- The full brief is in `BRIEF.md`. Always read it before proposing anything.
- I need to understand and be able to justify every decision, not just have working code.

## Working rules (mandatory)

1. We work in small, incremental steps. A step is a change that can be reviewed and tested in a few minutes.
2. Before each step, explain to me in Spanish what you're going to do, why, which files you'll create or modify, and which commands you'll run. Then STOP and wait for my "OK". Don't run anything until I approve it.
3. Never chain steps. Even if the next one is obvious, finish, summarize and wait.
4. You may read files and run read-only commands (ls, cat, kubectl get, --help) without asking. Anything else needs my explicit approval: installing tools or dependencies, creating or deleting the cluster, docker build, kubectl apply or delete, helm install or upgrade, git commit.
5. When each step is done, tell me in Spanish:
   - what was done and in which files,
   - how I can check it myself (exact command and expected result),
   - what could go wrong,
   - 2 or 3 questions someone could ask me about this step, with a short answer. Write them only into `readme_personal.md` (git-ignored, never committed) and just mention in the chat that they were added.
6. Record every decision in `docs/DECISIONS.md`: the decision, the alternatives considered, why we chose it and its trade-offs. That file will later feed `DESIGN.md`.
7. Languages: explanations to me in Spanish. Code, comments, commits, `README.md`, `DESIGN.md` and `docs/DECISIONS.md` in English.
8. Scope: stick to the brief. If something is an extra, don't implement it: add it to "Open items" in `DESIGN.md` and tell me.
9. Verify instead of assuming. If a decision depends on an external fact (Bluesky APIs, model availability, tool versions), check it against the documentation or with a real test, and tell me what you checked.
10. Keep `docs/PROGRESS.md` up to date with the current step, what's done and what's pending, so we can resume in another session.
11. After each approved and verified step, propose a commit with a clear message (Conventional Commits) and wait for my OK.
12. If something fails, don't improvise big fixes: explain the error, propose one or two options and wait.

## Technical starting point

> The decisions recorded in `docs/DECISIONS.md` supersede this section. It is kept as the original starting point.

These are proposals, not final decisions. Review them with me in step 0 and correct whatever doesn't hold up.

- **Local cluster:** k3d, because k3s enforces NetworkPolicies without extra configuration. Confirm this.
- **Three namespaces:**
  - `ingest`: reads Bluesky. Egress to the internet, Postgres and DNS. No ingress.
  - `data`: PostgreSQL, the only bridge between zones.
  - `analysis`: the API with a minimal UI, the summary worker and the LLM server. Egress only to Postgres, the LLM and DNS. No internet. The LLM pod has no egress at all.
- **Security boundary:** default-deny NetworkPolicies in every namespace, plus a `make verify-boundary` target proving that a curl to Bluesky fails from `analysis` and succeeds from `ingest`.
- **Database:** least-privilege roles.
  - Ingestor: read subscriptions and write posts.
  - Analysis: manage subscriptions, read posts and write summaries.
  - Migrations with Alembic.
- **Ingestor:**
  - Handles via `app.bsky.feed.getAuthorFeed`, unauthenticated.
  - Hashtags via `app.bsky.feed.searchPosts`, using a Bluesky app password stored as a Secret only in `ingest`. Unauthenticated search usually returns 403: verify this.
  - Idempotent writes keyed on each post's URI.
- **Summary worker (in `analysis`):** for each subscription, classifies recent posts with the LLM and stores the sentiment label, the count per sentiment, the number of items, a short summary and `updated_at`. The API only reads precomputed summaries; if the LLM goes down, the last summary keeps being served with its timestamp.
- **LLM:** a small, local model. The brief says "Gemma 4 A2B": check which variant actually exists (probably Gemma 4 E2B) and justify the choice. Serve it with llama.cpp server or Ollama. The weights are downloaded only during `make build`, never at runtime.
- **API:** FastAPI with minimal HTML to subscribe, unsubscribe and see each subscription with its sentiment, number of items and last update. At least two replicas, readiness and liveness probes, a PodDisruptionBudget and rolling updates with maxUnavailable 0.
- **Packaging:**
  - Python 3.12+ with uv (workspace).
  - Multi-stage Dockerfiles with `uv sync --frozen` and a non-root user.
  - A Helm chart.
  - Images built locally inside `make build`, since the reviewer may be on an ARM Mac.
- **Makefile:** `make build` and `make start` are required. Also `make verify-boundary`, `make stop` and `make clean`.
- **Deliverables:**
  - `README.md`: prerequisites, build, run and verification.
  - `DESIGN.md`: decisions, security boundary, high availability, continuous updates, delivery to isolated environments and open items.
  - The repo as a zip.

## Step plan

Each step ends with a stop and my approval.

0. Read `BRIEF.md`. Summarize the requirements in a table (functional and non-functional), list ambiguities and open questions, review the technical proposals above and propose the final plan. Don't create or run anything.
1. Prerequisites: check which tools I have installed (docker, k3d, kubectl, helm, uv) and their versions, and propose how to install whatever is missing.
2. Repo skeleton: uv workspace, folder structure, Makefile with empty targets, skeletons of README, DESIGN, DECISIONS and PROGRESS, `.gitignore` and `git init`.
3. k3d cluster, namespaces, default-deny NetworkPolicies, test pods and `make verify-boundary`.
4. PostgreSQL in `data`, with schema, migrations and roles.
5. Handle ingestor, end to end into Postgres.
6. Hashtag ingestor with authentication.
7. Offline LLM server, with a quick classification smoke test.
8. Summary worker.
9. API and minimal UI.
10. High availability and updates: replicas, probes, PDB and rolling update. Demonstrate an update with no downtime.
11. `make build` and `make start` from a clean clone.
12. Final documentation: README, DESIGN with open items, a short section on how I used AI agents, time spent stated honestly, and a review of the zip.

Priority: if time runs out, first a slice that works end to end. Everything else goes into "Open items".
