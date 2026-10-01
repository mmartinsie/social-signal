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
  - Session 3: the same setup, in a new conversation after clearing the
    context. The agent resumed from `CLAUDE.md`, `PROGRESS.md`,
    `DECISIONS.md` and the code. From step 5.
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

### Step 4b: image pipeline, migrations and schema (session 2)

- **Agent proposed and built:**
  - one uv-based Dockerfile for all Python services;
  - the migrations member (programmatic Alembic, password from a file,
    lock timeouts);
  - the hook Job;
  - the build and deploy scripts.

  Before implementing, it found a second hook-ordering issue: the Job's
  NetworkPolicy would not exist on a first install.
- **Author decided:**
  - split step 4 again;
  - approve the schema and grants table as proposed;
  - move the migrator policy to the database chart;
  - tag images by content (option A), after asking what the tag was about;
    the agent explained it with the three options.
- **Problems found by testing:**
  - Two builds of identical code got different tags. The agent compared
    layers, history and the image index, found BuildKit's provenance
    attestation, and disabled it. After that, three builds give the same
    tag.
  - The migration Job's log was empty (no logging configuration without
    `alembic.ini`). The agent added it, which also exercised the update
    path: new tag, then the hook re-runs as a no-op.
  - Agent mistake: to check that a change in another service keeps the
    tag, it appended probe lines to files and reverted them with
    `git checkout`. That did not work for the new, untracked migrations
    file. The agent noticed from the output, removed the line by hand and
    confirmed that the tag returned to the original value.
- **Verified:**
  - the tag changes only when the image content changes;
  - the image runs as non-root, without uv, and works with a read-only
    root filesystem;
  - migration `0001` created the tables with the approved owner and
    grants;
  - a forced migration failure made Helm abort the upgrade and keep the
    previous revision;
  - `verify-boundary` 16/16;
  - 0 image pulls.

### Step 4c: database privilege checks (session 2)

- **Agent proposed and built:**
  - one `psql` pod per database role, in its own zone, with that zone's
    labels and Secret;
  - a `sql` check inside `BEGIN … ROLLBACK`, where *denied* only counts if
    PostgreSQL answers `permission denied`;
  - one cross-role lifecycle scenario using `SET LOCAL ROLE`, because the
    ingestor can only link posts to a subscription that the analysis zone
    created.
- **Author decided:** approved the proposal, including a controlled
  sabotage test.
- **Problem found before building:** from what it recalled of PostgreSQL's
  internals, the agent expected `ON CONFLICT (uri) DO NOTHING` to need
  `SELECT` on `uri`, which the ingestor lacks. It said so in the proposal
  instead of assuming either way. A rolled-back probe confirmed it
  (`permission denied`), and the PostgreSQL docs state it. The ingestor
  will use `ON CONFLICT DO NOTHING` without a target, so the grants stay
  unchanged.
- **Verified:**
  - `verify-boundary` passes 27/27, and no rows or tables are left behind;
  - sabotage: an extra `GRANT SELECT ON summaries TO ingestor` produced
    exactly one FAIL and a non-zero exit;
  - after the `REVOKE`, `\dp` matched the saved copy and the run passed
    27/27 again.
- **Checked against documentation:** the `SET ROLE` privilege semantics and
  the `ON CONFLICT` privilege rules (postgresql.org).

### Step 5a: handle ingestor code (session 3)

- **Agent proposed** to split step 5 into 5a (code, unit tests and a real
  call to Bluesky) and 5b (image, CronJob and end to end in the cluster).
  Before proposing, it checked the shape of real `getAuthorFeed` responses,
  its error answers and the library versions.
- **Agent mistake, corrected when the author asked:**
  - It reported that 25 of 30 items in a sample were replies and
    recommended including them, as if they were one kind of post.
  - The author asked what replies were. The agent then split them: 23 were
    the author's own threads and 2 were replies to other accounts.
  - It found the `posts_and_author_threads` filter in the API's lexicon,
    measured the three relevant filters on the same account, and revised its
    recommendation.
- **Author decided:**
  - exclude replies to other accounts: without the post they answer, the
    context is lost, and many replies on social networks are sarcastic;
  - include the author's own threads;
  - httpx as the HTTP client, and unit tests with pytest.
- **Found by testing:**
  - Bluesky silently ignores an unknown `filter` value, so a typo would bring
    back the replies to other accounts. The ingestor validates it at
    start-up.
  - Malformed and unknown accounts both answer 400. With `limit` and
    `filter` validated, a 400 can only mean a bad subscription, which is
    logged as a warning and does not fail the run.
- **Verified:**
  - 25 unit tests pass;
  - a real call on `@bsky.app` kept 42 posts, all by that account, and
    skipped 4 reposts;
  - uv accepts a `dev` dependency group in the virtual workspace root.

  The database writes are tested in step 5b, inside the cluster.

### Step 5b: ingestor image and CronJob (session 3)

- **Author decided:** "do 5b", following the plan the agent had outlined
  when it proposed 5a:
  - the CronJob;
  - the image in `make build`;
  - `make start`;
  - a demo subscription created as `analysis`;
  - two manual runs to show idempotency;
  - `verify-boundary`.

  The agent restated the plan before running anything.
- **Agent built:**
  - the CronJob template (every 5 minutes, `Forbid`, no immediate retry, a
    run deadline shorter than the interval, the migration Job's hardening);
  - the chart values;
  - the new entry in `APP_IMAGES`.
- **Agent added a check that was not in the plan, and reported it:** a
  temporary Job pointed at a private IP. It proved the failure path: the
  NetworkPolicy rejects the connection, the run exits 1 and the Job ends
  `Failed`. The Job was deleted afterwards.
- **Observed, not foreseen:** the manual Jobs had disappeared when the
  agent went to delete them. The CronJob events showed why: the controller
  adopts Jobs created with `--from=cronjob` and prunes them with its
  history limit.
- **Verified:**
  - the image is non-root, runs with a read-only filesystem and no network,
    and contains no sources, tests or uv;
  - first run: 42 new posts; second run: 0; the unknown account gave only a
    warning;
  - a scheduled run completed on its own;
  - `verify-boundary` 27/27;
  - 0 image pulls.

### Step 6a: hashtag ingestor code (session 3)

- **Agent found that a recorded "verified fact" was wrong.** Before
  proposing, it re-checked hashtag search with real calls:
  - `api.bsky.app` answered 200 without a token, and 500 with one. Step 0
    had recorded that search needed a token on that host, from secondary
    sources, without a real test.
  - The Bluesky docs say those hosts do not support authentication.
  - bsky-docs #332 shows that the 403 is a deliberate load block that
    Bluesky turns on and off.

  The agent reported the contradiction, corrected the record, and marked
  the old row as wrong instead of deleting it.
- **Agent refused a shortcut:** the issue documents a way around the block
  (changing the case of the method name). The agent flagged it as
  deliberately bypassing Bluesky's load control and excluded it.
- **Agent proposed** four options for A6 and recommended the hybrid one: a
  separate CronJob every 15 minutes, because `createSession` allows 300
  logins per day, and the same reply rule as for handles.
- **Author decided:**
  - the hybrid approach;
  - the same reply rule;
  - asked why every 15 minutes: the agent showed the logins-per-day
    arithmetic, and the schedule is decided in 6b;
  - the author will provide an app password in `.env` for the real
    authenticated test.
- **Found by testing:**
  - To define "own thread", the agent compared its rule with the API's
    `posts_and_author_threads` filter. A first count seemed to differ
    (36 against 35). Over the same time span, both rules (parent only, and
    parent plus root) matched the API exactly (67 of 67), so the difference
    was a page-boundary artefact.
- **Verified:**
  - 53 unit tests pass, including the hybrid logic against a fake Bluesky;
  - a real unauthenticated search for `#python` through the ingestor's code
    worked on `api.bsky.app` and raised `SearchForbidden` on
    `public.api.bsky.app`;
  - the authenticated path worked with the author's app password.
- **Handling of the secret:**
  - The author created `.env` by hand and wrote the app password in it; it
    never went through the conversation.
  - The agent did not open the file. It checked its mode (600) and that
    git ignores it.
  - It ran a throwaway script, outside the repository, that printed only
    the DID, the PDS host, the password's length and the result counts.

### Step 6b: credentials Secret and hashtag CronJob (session 3)

- **Author decided:**
  - a schedule of every 20 minutes for hashtags rather than the proposed
    15, to leave room for manual runs (72 logins a day);
  - "do it" for 6b.

  The agent restated the plan before running anything. The author had not
  answered whether quotes should be accepted in `.env`. The agent chose to
  strip one surrounding pair, and said so.
- **Agent built:**
  - `scripts/bluesky-secret.sh`;
  - one template for both CronJobs;
  - the Helm helpers that had been pending since D19;
  - the Makefile hook.
- **Agent verified its own claim:** the script avoids `kubectl apply`
  because the agent expected it to copy the password in clear text into an
  annotation. The agent confirmed it with a fake Secret before recording
  it.
- **Tests the agent added beyond the plan, and reported:**
  - the script's parsing, with a fake `kubectl` and fake files, before
    touching the cluster;
  - a Job pointed at `public.api.bsky.app`, where Bluesky's search block is
    active, to see the real warning path.
- **Secret handling:**
  - The agent never printed the password.
  - To prove that it appears in no log or Helm release, it read it into a
    shell variable and counted matches with `grep -F`. The value was
    therefore briefly a command argument on the author's own machine,
    though never printed. The product scripts never pass it as an
    argument.
- **Verified:**
  - both hashtag paths end to end, plus the blocked path;
  - the Secret only in `ingest`, only mounted by `ingestor-hashtags`, with
    no annotation;
  - `verify-boundary` 27/27;
  - 0 image pulls.

### Step 7a: the LLM image (session 3)

- **Agent checked before proposing:**
  - which Gemma 4 E2B GGUF files exist, whether they are gated, and their
    sizes, checksums and licences (Hugging Face API);
  - whether the file downloads without a token (response headers only);
  - llama.cpp's image tags and platforms, its `gemma4` support, and the
    server's options (`--offline`, `--reasoning`, `/health`, JSON schema
    output).

  It found that Google publishes an official QAT Q4_0 GGUF under Apache
  2.0.
- **Author decided** the agent's three recommendations: the official QAT
  file, one LLM replica with `Recreate`, and splitting the step in two.
- **Agent built:** `scripts/fetch-model.sh`, `docker/llm.Dockerfile`, the
  `model` target, and a `bundle_image` function in `build-images.sh` that
  the Python images and the LLM image share.
- **The author noticed an apparent hang.** The agent had said "about 2
  minutes" for the build, and `--quiet` showed nothing while Docker spent
  about 6 minutes compressing the 3.35 GB layer. The agent inspected the
  running processes and the disk writes and explained it; nothing was
  stuck. Its time estimate had been wrong.
- **Found by testing:**
  - The non-root server could not open the model. `COPY --chmod=0444` had
    also given mode 0444 to the `/models` directory. The agent fixed the
    Dockerfile.
  - Before rebuilding (8 minutes), the agent ran the quality evaluation on
    the first image, started as root only for that run: if E2B had failed,
    a rebuild with E4B would have been needed anyway.
  - The `response_format` shape documented in llama.cpp's README was
    ignored by v0.5.0. The agent compared three shapes against the running
    server and chose OpenAI's, which is enforced.
  - Agent mistake: its readiness loop in the shell waited for a log line
    that the server never prints. It reported a load time of 247 s; the
    server's own log showed 44 s. The documented figure is 44 s.
- **Verified:** 14 of 14 on a small labelled set (sarcasm and Spanish
  included), a median of 2.95 s per post, 3.0-3.5 GiB of memory, and 98 s
  for one summary-sized prompt, which is input for step 8.
- **Agent hypothesis refuted by its own test.** The final non-root smoke
  test used a shortened sarcastic post, which came out positive.
  - The agent first attributed this to its shorter prompt. It re-ran the
    test with the evaluation's prompt and the post still failed.
  - A third run, with both wordings on the corrected image, showed that the
    wording is the cause: with the explicit complaint the post is
    negative, without it positive.

  The documents now say that 14 of 14 is optimistic, and a proper
  evaluation is an open item.
- **Interrupted build.** A reset of the VS Code session killed `make` during
  `docker save`. The script had already deleted the previous tarball, so
  `images.txt` pointed to a file that no longer existed. The agent found
  it, changed the script to delete old tarballs only after the new one is
  complete, and re-ran the target (the build came from the cache).
- **Author decided:**
  - delete the old local image with the permission bug;
  - version the evaluation.

  The agent turned its throwaway script into `tools/llm_eval.py`, added
  the failing sarcastic post as a known hard case, and ran it exactly as
  its docstring documents: 14 of 15.

### Step 7b: the LLM in the cluster (session 3)

- **Author decided:** "do it", following the plan the agent had outlined.
  The agent restated it before running anything.
- **Agent built:**
  - the `llm` Deployment (1 replica, `Recreate`) and Service;
  - four LLM checks in `verify-boundary`;
  - `scripts/llm-smoke.sh` with a `make llm-smoke` target. Its
    label-parsing `grep` was tested on a canned reply before touching the
    cluster.
- **Long-running steps made visible.** After the "hang" in step 7a, the
  agent ran `make start` in the background with a timestamp on every log
  line, watched it with a monitor that also matched failures, and gave
  the author a one-line `tail -f` command. When the author asked how long
  it would take, the agent answered from the log's progress and said it
  was an estimate.
- **A suspicion checked and withdrawn:** copies of old tarballs in k3d's
  shared volume suggested that the 3.5 GB copy would stay there too. After
  the import it was gone; only 104 MB from an earlier import remained.
- **Verified:**
  - the import took 9 minutes, in parallel into the three nodes, and each
    node's containerd grew to about 8.5 GB;
  - the model loaded in 39 s and uses 3.5 GiB;
  - `verify-boundary` 31/31, `make llm-smoke` 3/3;
  - 0 image pulls.

### Step 8: the summary worker (session 3)

- **Author decided, from options the agent proposed:**
  - **Ties are `neutral`**, in every combination. The agent had proposed
    `neutral` too, and argued against "negative wins".
  - **The LLM sentence is kept, but made cheaper,** as the agent proposed:
    only when the posts change, over the 20 most recent posts cut to 280
    characters.
  - **Every 5 minutes.** The author asked whether that was too often. The
    agent answered that the schedule does not change how much the LLM
    works, since each post is classified once, and showed the alternatives
    in a table.
  - **`updated_at` is when the summary was generated.** The agent had
    proposed "last checked"; the author chose otherwise, and the agent
    recorded the trade-off.
  - **Steps 8a, 8b and 8c done in one go**, at the author's request, instead
    of stopping after each.
- **Author's question:** why not classify "in the middle of the ingestor's
  run"? The agent answered both readings:
  - classifying inside the ingestor breaks the boundary;
  - a notification through PostgreSQL would keep it, but is not worth the
    complexity now. It is an open item.
- **Agent built:**
  - the worker package: `llm.py`, `store.py`, `summary.py` and
    `__main__.py`;
  - 43 unit tests with fakes, including the time budget and every failure
    path;
  - the `worker` CronJob and its values; the chart refuses a budget that
    cannot fit in the Job's deadline;
  - the worker image in `make build`;
  - `tools/llm_eval.py` changed to import the worker's client, so the
    evaluation and the worker cannot drift apart.
- **Verified before deploying:**
  - the cron expression, server-side with `--dry-run=server`, which also
    rejected a malformed one;
  - the SQL, run as `analysis` in `postgres-0` and rolled back.
- **Agent estimate wrong, found by measuring.** The agent told the author
  that the current posts would fit in one run, at about 2.7 s per post.
  The first run used up its budget after 34 posts. The agent then measured
  from `classified_at`: the time grows with the post's length, from about
  2.5 s for 40 characters to 5-8 s near 300. Real `#python` posts average
  198 characters, while the earlier figures came from short test
  sentences. The design already handled it: the next run finished the
  rest. The documents now say "2.5 to 8 s per post".
- **Failure path tested in the cluster:** the agent scaled the LLM to 0,
  let a scheduled run find it down, checked that both summaries kept their
  `updated_at`, and scaled it back.
- **Side finding:** an ingestor Job from earlier in the session was marked
  `Failed` (`DeadlineExceeded`) although its pod had succeeded. It
  happened during the 9-minute import of the LLM image: the API server was
  timing out under disk load. The agent reported it to the author without
  changing anything.

### Step 9: the API and the minimal UI (session 3)

- **Author decided:** accept every recommendation of the plan, do 9a and
  9b in one go, and make sure what already works stays as it is.
- **The agent made "untouchable" checkable.** Before starting it saved
  checksums of the NetworkPolicies, the database chart, the migration and
  the platform manifests. At the end it compared them, confirmed that no
  file under the other services, the shared package or the scripts had
  changed, and re-ran `verify-boundary` and `llm-smoke`.
- **The agent changed its own plan, and said so:** it dropped the
  `psycopg-pool` it had proposed in favour of one connection per request
  with the existing shared `connect()`. That is simpler, recovers by itself
  after a database restart, and leaves the shared package untouched.
- **Verified before writing code:**
  - the dependencies' latest versions on PyPI, and FastAPI's own
    requirements;
  - the AT Protocol's handle syntax and the hashtag limits, in the atproto
    source and lexicons;
  - Starlette 1.7's template autoescaping and response signature, in the
    installed source.
- **Agent built:**
  - the API package and a server-rendered page, with no JavaScript and no
    external assets;
  - 52 unit tests, including an escaped `<script>` in the LLM's sentence
    and a refused cross-site post;
  - the Deployment, Service and Ingress.
- **Side effect noticed and checked:** the new lock file gave the other
  Python images new tags. The agent compared the old and new images
  (package list and source files hashed): identical. It also diffed the
  rendered release against the deployed one: only those tags and the new
  API objects differed.
- **Tested in the cluster:**
  - the whole flow through the form, from "waiting for the first posts" to
    a summary, then the unsubscribe and its cascade;
  - a cross-site post (403), an invalid value (400), a duplicate (200);
  - PostgreSQL scaled to 0, timed between an ingestor run and a worker run
    so as not to break either: 503 page, pods still ready, recovery
    without a restart;
  - from another pod the API is refused; through Traefik it answers.
- **Not done, recorded for later:** that check of the API's ingress is
  not in `verify-boundary` yet; the agent left the script unchanged and
  listed it as a follow-up.

### Step 10: high availability and updates without downtime (session 3)

- **Author decided:** "do step 10". The agent wrote its plan in the chat
  before changing anything, then carried it out.
- **The agent widened the scope, and said why:** before writing anything
  it traced the analysts' path in the cluster and found that Traefik and
  CoreDNS, both k3s defaults, ran one pod each, so two API replicas alone
  would not survive a drain. It made both highly available with k3s'
  supported mechanisms (a `HelmChartConfig`; scaling a count k3s leaves
  out of its manifest, checked in k3s' recorded object).
- **Verified before writing:** the `preStop` sleep action against the API
  server (dry run), the bundled Traefik chart's values (read from the chart
  k3s serves), and uvicorn's shutdown code.
- **The first drain demo failed (86 of 356), and the agent investigated
  instead of retrying.** It formed hypotheses and tested each with probes
  on every node's port 80:
  - cordoning alone, creating and deleting pods, deleting a finished Job's
    pod: none failed, so those were ruled out;
  - it noticed that `kubectl drain` reports "evicted" only once a pod is
    gone, which had misled its first reading of the timeline;
  - it found Traefik closing its listener on SIGTERM, and fixed it with a
    `preStop`;
  - it traced the last failure to a CoreDNS pod stopping at once, and
    added a DNS retry to the API instead of editing k3s' own CoreDNS.
  Each fix was measured: 86 → 1 → 0 failures.
- **Agent mistake, found by itself:** the first version of the demo
  stopped the load before the old pods had finished stopping, which is
  exactly when failures happen. It fixed the script and re-ran the demo.
- **A hypothesis withdrawn:** it first suspected node updates triggering a
  network policy resync; a cordon-only test disproved it.
- **One observation left unexplained and documented:** a 3 s burst of 502s
  after an uncordon, seen once before Traefik's fix and not again.
- **Side finding:** the machine's clock jumped by about six hours during
  the step, probably a suspend; the agent noted it so that the logs' times
  are not misread.

### Step 11: from a clean clone (session 3)

- **Author decided:** "do it", after the agent warned that the test meant
  deleting the cluster and its data, and taking 15-25 minutes. Midway, the
  author asked whether to copy `.env` into the clone. The agent proposed
  to test without it first, as a reviewer would, then copy it (with
  `cp -p`, without reading it) to test the credentials path. The author's
  idea and the agent's order were both kept.
- **Checked before starting:** free space where the WSL disk actually
  lives (drive D:, not the nearly full C:).
- **Ran and timed:** `make build` (12.5 minutes) and `make start` (23
  minutes) in the clone, with milestone monitors instead of silent waits;
  then every check and both demos on the new cluster. Nothing in the
  repository had to be fixed.
- **Security incident, the agent's mistake.** To confirm that the Bluesky
  Secret had no `last-applied` annotation, the agent ran `kubectl get
  secret -o go-template` with a template that failed on a missing field.
  kubectl then printed the whole object, base64 values included, into the
  agent's session. The agent:
  - stopped all work and told the author at once, in plain words, without
    repeating the value;
  - recommended revoking the app password, and gave the exact steps;
  - saved a rule in its persistent memory: Secrets are inspected only with
    `kubectl describe`, which never prints values;
  - after the author rotated the password, copied the new `.env` and ran
    `make start`, checked the Secret with `describe` (key names and sizes
    only), and confirmed the login.
  The design held: the value never reached git, an image, a log or Helm.
  The leak came from how the agent inspected it.
