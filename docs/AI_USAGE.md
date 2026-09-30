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
  could go wrong, and likely questions about it. The questions are not part
  of the repository: at the author's request they are also collected in a
  personal, git-ignored study file (`readme_personal.md`).
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

### Step 3a: offline image bundle (session 2)

- **Agent proposed** to do step 3 in two parts: the cluster with default-deny
  first, then the allow rules and `verify-boundary`. It also proposed a local
  k3d registry to get images into the cluster.
- **Author decided:**
  - split step 3;
  - drop the registry: `make build` downloads the images into a local folder
    and `make start` runs them from there, so the deployment host needs
    access only to Bluesky, not to Docker Hub. For the timebox this is
    better than a Harbor-like registry;
  - namespaces and default-deny are applied with `kubectl apply`;
  - `make start` must not switch the user's current kubectl context.
- **Agent re-planned** step 3 into 3a (bundle), 3b (cluster from the bundle)
  and 3c (allow rules and verification), because the bundle added work. It
  then verified the external facts the design depends on (listed in
  [`DECISIONS.md`](DECISIONS.md#5-verified-facts)):
  - k3d pull behaviour, from its source;
  - the k3d helper-image variables;
  - k3s air-gap import;
  - the release assets and checksums;
  - multi-arch availability.
- **Process note:** the agent took an ambiguous "yes" as approval and tried
  to run `make build`. The author rejected that tool call, and the agent
  asked for explicit approval before retrying.
- **Verified:**
  - `make build` produced a 319 MB bundle for amd64;
  - the k3s tarball's sha256 matches the release file;
  - a second run downloads nothing;
  - every image tarball is an OCI archive holding only the requested
    platform;
  - the checksum comparison catches a truncated file.

### Step 3b: cluster from the bundle, namespaces and default-deny (session 2)

- **Agent proposed and built:**
  - the k3d config;
  - the platform manifests;
  - `scripts/cluster-up.sh`;
  - the `start`, `stop`, `clean` and `distclean` targets;
  - a check after `k3d image import`, because its source showed that it
    exits 0 even when a node fails.
- **Author decided:**
  - `make clean` keeps the bundle and `make distclean` removes it (D10);
  - Traefik moves off port 8080;
  - block all image pulls in the cluster;
  - wait for stable nodes;
  - the local copies of the images are removed from Docker before testing.
    The author did this by hand, with the command the agent gave.
- **Problems found by testing, not foreseen by the agent:**
  - The author ran `kubectl` before the cluster existed and saw it fall back
    to `localhost:8080`, the port the agent had planned for Traefik (D8).
  - The first `make start` succeeded, but pod events showed that k3s had
    pulled its system images from Docker Hub. The air-gap import is
    asynchronous and slow on the author's HDD, so the offline promise was
    not being met. The agent reported it instead of papering over it,
    offered to enforce or to document, and the author chose to enforce (D9).
  - `make stop` then `make start` failed: an agent node got a new IP and
    crash-looped while the script was importing. The script's own
    verification caught it, and the fix is to wait for stable nodes (D11).
- **Verified:**
  - `make start` from scratch takes about 4.5 minutes on the HDD;
  - there are 0 `Successfully pulled` events; images from `docker.io` and
    `registry.k8s.io` fail against `offline.invalid`;
  - after `make stop`, `make start` succeeds in about 2 minutes despite a
    node IP change;
  - default-deny: `analysis` cannot resolve DNS, while `default` gets
    HTTP 200;
  - Traefik answers 404 on `127.0.0.1:8088`.

### Step 3c: per-component allow rules and `make verify-boundary` (session 2)

- **Agent proposed and built:**
  - the Helm chart with the six NetworkPolicies of A5;
  - the verification script, using curl pods that carry each component's
    labels;
  - the Helm step in `make start`.

  Before writing the policies it verified the real CoreDNS and Traefik
  labels, the private address behind the Kubernetes API, and Helm 4's
  `--wait` semantics. It also validated the chart with `helm lint` and a
  server-side dry run.
- **Author decided:** limit the ingestor's egress to TCP 443 and exclude the
  private and link-local ranges (refinement of A5).
- **Problem found by testing:** the first run failed 1 of 9 checks. The LLM
  pod was expected to fail at DNS (curl exit 6) but timed out (exit 28),
  because curl's connect timeout also covers name resolution. The policy
  was right; the test's classification was ambiguous. The agent explained
  it and added a separate DNS check (`timeout 5 nslookup`), after confirming
  that the curl image ships those tools. This small fix inside the approved
  test script was applied without a separate approval round.
- **Author asked** for the likely questions about each step to be
  collected, with
  answers, only in the git-ignored `readme_personal.md` from now on. Rule 5
  of `CLAUDE.md` was updated accordingly.
- **Verified:**
  - `make verify-boundary` passes 11/11 in about 17 s and deletes its pods;
  - `make start` is idempotent (about 32 s on a running cluster; Helm
    revision 2).

### Step 4a: PostgreSQL release, roles and credentials (session 2)

- **Agent found a flaw in an approved decision before implementing it:** D1
  put the migration in a `pre-install` hook of the same chart as
  PostgreSQL, but Helm runs those hooks before creating any resource. It
  proposed three fixes and recommended a separate database release.
- **Author asked** how PostgreSQL could be upgraded on its own. The agent
  explained minor versus major upgrades, checked the CloudNativePG
  documentation and the `pg_upgrade` helper images, and proposed
  documenting it.
- **Author decided:**
  - one PostgreSQL pod, justified by stating that any upgrade means an
    outage today, and documenting how it would be upgraded and scaled, with
    no upgrade demo;
  - split step 4;
  - download `postgres:18.6-alpine3.23`;
  - credentials option 2 (generated by `make start`), chosen from four
    options the agent laid out;
  - every discussed point also goes into the personal question sheet.

  The agent had also suggested enabling k3s secrets encryption; the author
  did not take it up, so it went to open items.
- **Agent built:**
  - the `socialsignal-db` chart;
  - `scripts/db-secrets.sh`;
  - the TCP and "outsider" checks in `verify-boundary`;
  - the two-release `make start`.
- **Problem found by testing:** the agent's first login test connected
  through `127.0.0.1` and a *wrong* password succeeded. The official image
  trusts localhost in `pg_hba.conf`, so that test proved nothing. The agent
  spotted it because it included a negative case, and repeated the test
  over the pod IP, where SCRAM-SHA-256 applies.
- **Verified:**
  - over the network, each role logs in only with its own Secret;
  - no password appears in the pod spec or the Helm releases;
  - the roles have no special privileges;
  - `verify-boundary` passes 16/16;
  - after deleting the pod, it is back in about 6 s, with its data intact
    and without re-running the init script;
  - 0 image pulls.
