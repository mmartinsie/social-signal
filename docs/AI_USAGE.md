# AI usage

The brief encourages the use of AI agents and asks the author to be able to
defend the result. This file is a running log of how AI was used, step by
step. It feeds the "How AI agents were used" section of
[`DESIGN.md`](../DESIGN.md).

The system itself calls no external LLM: sentiment analysis runs on a local
model (see [`DECISIONS.md`](DECISIONS.md#a1-which-small-local-llm-and-how-to-serve-it)).
This file is only about the *development* process.

## Tools

- **Claude Code** (Anthropic), model **Claude Opus 5.5** with the
  "extra high" effort setting, in every session so far:
  - Session 1: Claude Code on Windows. Steps 0 and 1.
  - Session 2: the Claude Code extension for VS Code, running inside WSL2
    (Ubuntu 24.04). From step 2.
- Commits written with the agent carry a
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` trailer.

## Working protocol

The rules for the agent are versioned in [`CLAUDE.md`](../CLAUDE.md). In
short:

- Work in small steps. Before each step the agent explains, in Spanish, what
  it will do, why, which files it touches and which commands it runs, then
  waits for the author's explicit approval.
- The agent may run read-only commands freely. Installing anything, building
  images, changing the cluster, running Helm and committing all need
  approval.
- Every decision goes to [`DECISIONS.md`](DECISIONS.md) and the state goes to
  [`PROGRESS.md`](PROGRESS.md).
- External facts (APIs, model availability, tool versions) are verified
  against documentation or with a real test, never assumed.
- After each step the agent reports what changed, how to verify it, what
  could go wrong, and likely questions about it. The questions stay in the
  chat, never in the repository.
- On failure the agent explains the error and proposes one or two options
  instead of improvising large fixes.

**Continuity between sessions.** Claude Code keeps a persistent memory
outside the repository. When moving from Windows to WSL, the author also
wrote a handoff prompt summarising the state and the decisions (A1-A11). From
step 2 on, the repository documents are the source of truth, and the agent's
memory is trimmed so it does not duplicate them.

## Log

### Step 0: brief analysis and plan (session 1)

- **Agent:** summarised the functional and non-functional requirements,
  listed the ambiguities in the brief, reviewed the technical proposals in
  `CLAUDE.md` and verified the external facts they depended on (Gemma 4
  variants, Bluesky search authentication, NetworkPolicy enforcement in k3s,
  llama.cpp images, the Bitnami catalogue). The sources are in
  [`DECISIONS.md`](DECISIONS.md#5-verified-facts).
- **Author:** decided A1-A11 and D1-D6.
- **Changes to the starting proposals in `CLAUDE.md`:**
  - "Gemma 4 A2B" confirmed as non-existent; E2B chosen, served by llama.cpp
    rather than Ollama.
  - PostgreSQL from the official image rather than Bitnami.
  - DNS egress restricted to the CoreDNS pods.
  - `verify-boundary` also tests a raw public IP and waits for policy
    propagation.
  - Ingestor and worker as CronJobs.
  - Classification results in a separate `post_sentiments` table.
  - A dedicated `migrator` database role.

### Step 1: prerequisites (session 1)

- **Agent:** checked which tools were installed and their versions, and
  proposed how to install the missing ones.
- **Outcome:** the environment in [`DECISIONS.md`](DECISIONS.md#3-development-environment-step-1)
  (E1-E4): WSL2 on D:, Docker Engine inside WSL, and the pinned tool
  versions. The repository moved from the Windows filesystem to `~/social-signal` in
  WSL; the Windows copy is kept only as a backup.

### Step 2: repository skeleton (session 2)

- **Handoff:** the author gave the agent a handoff prompt. The agent read
  `CLAUDE.md`, `BRIEF.md` and its memory, and confirmed that the memory
  matched the handoff. The memory lacked two details, which it took from the
  handoff: DNS tunnelling as an open item, and the order in which features
  are cut.
- **Agent proposed:**
  - the uv workspace layout (one member per deployable plus a shared
    package);
  - Makefile placeholders;
  - skeletons of `README.md`, `DESIGN.md`, `DECISIONS.md` and `PROGRESS.md`;
  - this log.
- **Author decided:**
  - the project name `socialsignal` (the agent had proposed `feedsense`);
  - versioning `BRIEF.md` and `CLAUDE.md` so the use of AI stays traceable;
  - placeholders that fail (the recipe exits with status 1);
  - `DECISIONS.md` organised around A1-A11, and an "Assumptions" section in
    `DESIGN.md`;
  - `DECISIONS.md` supersedes the "Technical starting point" of `CLAUDE.md`.
- **Agent drafted:** the *Options / Why / Trade-off* text in `DECISIONS.md`,
  from the approved decisions. The author committed the skeleton before
  reviewing that text, so the review is still a follow-up in
  [`PROGRESS.md`](PROGRESS.md).
- **Verified:**
  - the `uv_build` constraint, taken from the output of `uv init --package`
    with uv 0.12.21;
  - a virtual workspace root with no `[project]` table resolves
    (`uv lock`), and all four members install and import
    (`uv sync --all-packages`);
  - every text file is checked out with LF (`git check-attr`);
  - the Makefile placeholders fail as intended. Only tested with GNU
    make 4.3; make 3.81 compatibility is by construction and has not been
    tested.
