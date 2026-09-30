#!/bin/sh
# Prove the security boundary against the real NetworkPolicies. For each
# component identity it starts a curl pod carrying that component's labels
# (so exactly the same policies apply as to the real pods, whose images have
# no curl), tries to reach the internet and PostgreSQL, and compares the
# outcome with what the policies should allow. An "outsider" pod in the
# `default` namespace, which has no policies, checks the database's own
# ingress rule. Prints a PASS/FAIL table; exits 1 on any FAIL.
#
# Three kinds of check:
#   dns      `nslookup` with a timeout: "resolves" or "no-dns".
#   connect  curl exit code: 0 = "open" (any HTTP answer counts),
#            7 / 28 = "blocked" (refused or timed out).
#   tcp      curl's time_connect on a telnet:// URL: > 0 = "open" (the TCP
#            handshake completed), 0 = "blocked". Used for PostgreSQL, which
#            never answers a bare connection, so the exit code says nothing.
# A curl timeout (28) cannot tell a dropped DNS query from a dropped
# connection, so DNS is checked on its own: for api, "resolves" plus
# "blocked" proves the NetworkPolicy, not DNS, is what stops it.
#
# The database privileges are the second layer. One psql pod per database
# role runs in that role's zone, with that zone's labels and only that zone's
# Secret, and logs in over the network (SCRAM; never 127.0.0.1, which the
# image trusts without a password). A fourth kind of check:
#   sql      the SQL runs inside BEGIN ... ROLLBACK, so nothing is committed:
#            "allowed" = it succeeds, "denied" = it fails with "permission
#            denied". Any other error is a FAIL, so a typo or a constraint
#            violation can never pass as "denied".
# One scenario needs two roles in turn (the ingestor can only link a post to
# a subscription the analysis zone created). It runs as a single rolled-back
# transaction inside postgres-0, where the superuser switches identity with
# SET LOCAL ROLE: every privilege is then checked as that role.
#
# Inputs (environment, set by the Makefile): KUBE_CONTEXT, CURL_IMAGE,
# POSTGRES_IMAGE
# POSIX sh on purpose: it must run with both Linux and macOS userland.

set -eu

: "${KUBE_CONTEXT:?}" "${CURL_IMAGE:?}" "${POSTGRES_IMAGE:?}"
kubectl="kubectl --context $KUBE_CONTEXT"

BLUESKY_HOST=public.api.bsky.app
BLUESKY=https://$BLUESKY_HOST/xrpc/_health
PUBLIC_IP=https://1.1.1.1
KUBE_API=https://kubernetes.default.svc
POSTGRES=postgres.data.svc:5432
DB_HOST=postgres.data.svc.cluster.local
DB_NAME=socialsignal

# name:namespace:component, one test pod per identity. "outsider" matches no
# policy and lives in a namespace without default-deny.
PODS="vb-ingestor:ingest:ingestor vb-api:analysis:api vb-worker:analysis:worker vb-llm:analysis:llm vb-outsider:default:outsider"
# name:namespace:component:secret, one psql pod per database role.
PSQL_PODS="vb-db-ingestor:ingest:ingestor:db-ingestor vb-db-analysis:analysis:api:db-analysis"
TEST_LABEL=socialsignal/test=verify-boundary

delete_pods() {
  for entry in $PODS $PSQL_PODS; do
    IFS=: read -r name ns _ <<EOF
$entry
EOF
    $kubectl delete pod "$name" -n "$ns" --ignore-not-found --wait="$1" >/dev/null 2>&1 || true
  done
}
trap 'delete_pods false' EXIT
trap 'exit 130' INT TERM

# Leftovers from an interrupted run would make `kubectl run` fail.
delete_pods true

echo "Starting one test pod per component identity..."
for entry in $PODS; do
  IFS=: read -r name ns component <<EOF
$entry
EOF
  $kubectl run "$name" -n "$ns" --image="$CURL_IMAGE" --image-pull-policy=Never \
    --restart=Never --labels="app.kubernetes.io/component=$component,$TEST_LABEL" \
    --command -- sleep 600 >/dev/null
done
# `kubectl run` cannot read an env var from a Secret, hence a manifest.
for entry in $PSQL_PODS; do
  IFS=: read -r name ns component secret <<EOF
$entry
EOF
  $kubectl create -f - >/dev/null <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $name
  namespace: $ns
  labels:
    app.kubernetes.io/component: $component
    ${TEST_LABEL%%=*}: ${TEST_LABEL#*=}
spec:
  restartPolicy: Never
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    runAsUser: 70
    runAsGroup: 70
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: psql
      image: $POSTGRES_IMAGE
      imagePullPolicy: Never
      command: [sleep, "600"]
      env:
        - name: PGHOST
          value: $DB_HOST
        - name: PGDATABASE
          value: $DB_NAME
        - name: PGCONNECT_TIMEOUT
          value: "5"
        - name: PGUSER
          valueFrom:
            secretKeyRef: {name: $secret, key: username}
        - name: PGPASSWORD
          valueFrom:
            secretKeyRef: {name: $secret, key: password}
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: [ALL]
EOF
done
for entry in $PODS $PSQL_PODS; do
  IFS=: read -r name ns _ <<EOF
$entry
EOF
  $kubectl wait --for=condition=Ready "pod/$name" -n "$ns" --timeout=120s >/dev/null
done
# k3s applies policies to a new pod a few hundred ms after it starts
# (k3s issue #14711); give it margin so we never test an unprotected pod.
sleep 5

failures=0
checks=0
record() { # pod namespace target expected got
  checks=$((checks + 1))
  if [ "$5" = "$4" ]; then
    result=PASS
  else
    result=FAIL
    failures=$((failures + 1))
  fi
  printf '%-5s %-11s %-10s %-48s expected %-9s got %s\n' \
    "$result" "${1#vb-}" "$2" "$3" "$4" "$5"
}

check_dns() { # pod namespace hostname expected
  # Trailing dot: query the name as-is, without the search-domain list.
  if $kubectl exec "$1" -n "$2" -- timeout 5 nslookup "$3." >/dev/null 2>&1; then
    got=resolves
  else
    got=no-dns
  fi
  record "$1" "$2" "dns $3" "$4" "$got"
}

check_connect() { # pod namespace url expected
  code=0
  $kubectl exec "$1" -n "$2" -- \
    curl -sk -o /dev/null --connect-timeout 5 --max-time 8 "$3" >/dev/null 2>&1 || code=$?
  case "$code" in
    0) got=open ;;
    7 | 28) got=blocked ;;
    *) got="error($code)" ;;
  esac
  record "$1" "$2" "$3" "$4" "$got"
}

check_tcp() { # pod namespace host:port expected
  seconds=$($kubectl exec "$1" -n "$2" -- \
    curl -s -o /dev/null -w '%{time_connect}' --connect-timeout 4 --max-time 5 \
    "telnet://$3" 2>/dev/null) || true
  case "$seconds" in
    "" | 0 | 0.0 | 0.000000) got=blocked ;;
    *) got=open ;;
  esac
  record "$1" "$2" "tcp $3" "$4" "$got"
}

run_sql() { # pod namespace [psql options...]; SQL on stdin. Sets $got.
  pod=$1 ns=$2
  shift 2
  code=0
  # stderr only: the error message, if any.
  error=$({ echo 'BEGIN;'; cat; echo 'ROLLBACK;'; } |
    $kubectl exec -i "$pod" -n "$ns" -- psql -X -q -v ON_ERROR_STOP=1 "$@" 2>&1 >/dev/null) ||
    code=$?
  if [ "$code" -eq 0 ]; then
    got=allowed
  elif printf '%s\n' "$error" | grep -q 'permission denied'; then
    got=denied
  else
    got=error
  fi
}

report_sql() { # who namespace description expected
  record "$1" "$2" "sql $3" "$4" "$got"
  if [ "$got" != "$4" ] && [ -n "$error" ]; then
    printf '%s\n' "$error" | sed 's/^/      /'
  fi
}

check_sql() { # pod namespace description expected; SQL on stdin
  run_sql "$1" "$2"
  report_sql "$1" "$2" "$3" "$4"
}

# Test rows. They never outlive their transaction.
POST_URI=at://did:plc:verifyboundary/app.bsky.feed.post/test
SUB_VALUE=verify-boundary.invalid
# Exactly how the ingestor will store posts: without a conflict target, which
# would need SELECT on the column (tested, D17).
INSERT_POST="INSERT INTO posts (uri, cid, author_did, author_handle, text, created_at)
  VALUES ('$POST_URI', 'test', 'did:plc:verifyboundary', '$SUB_VALUE', 'test', now())
  ON CONFLICT DO NOTHING;"
# How the worker will store a summary: insert, or update the existing one.
UPSERT_SUMMARY="INSERT INTO summaries (subscription_id, dominant_label, positive_count,
    neutral_count, negative_count, item_count, summary_text, updated_at)
  SELECT id, 'neutral', 0, 1, 0, 1, 'test', now() FROM subscriptions
  WHERE kind = 'handle' AND value = '$SUB_VALUE'
  ON CONFLICT (subscription_id) DO UPDATE SET dominant_label = EXCLUDED.dominant_label,
    positive_count = EXCLUDED.positive_count, neutral_count = EXCLUDED.neutral_count,
    negative_count = EXCLUDED.negative_count, item_count = EXCLUDED.item_count,
    summary_text = EXCLUDED.summary_text, updated_at = EXCLUDED.updated_at;"

echo
# Ingest zone: HTTPS to the internet, nothing private.
check_connect vb-ingestor ingest "$BLUESKY" open
check_connect vb-ingestor ingest "$PUBLIC_IP" open
check_connect vb-ingestor ingest "$KUBE_API" blocked
# Analysis zone: api and worker resolve names but cannot connect out.
check_dns vb-api analysis "$BLUESKY_HOST" resolves
check_connect vb-api analysis "$BLUESKY" blocked
check_connect vb-api analysis "$PUBLIC_IP" blocked
check_dns vb-worker analysis "$BLUESKY_HOST" resolves
check_connect vb-worker analysis "$BLUESKY" blocked
check_connect vb-worker analysis "$PUBLIC_IP" blocked
# The LLM has no egress at all, not even DNS.
check_dns vb-llm analysis "$BLUESKY_HOST" no-dns
check_connect vb-llm analysis "$PUBLIC_IP" blocked
# PostgreSQL, the only bridge between zones: reachable by the ingestor, the
# API and the worker; not by the LLM (its egress) nor by a pod outside the
# zones whose own egress is open (the database's ingress rule).
check_tcp vb-ingestor ingest "$POSTGRES" open
check_tcp vb-api analysis "$POSTGRES" open
check_tcp vb-worker analysis "$POSTGRES" open
check_tcp vb-llm analysis "$POSTGRES" blocked
check_tcp vb-outsider default "$POSTGRES" blocked

# Database privileges, per zone, with that zone's own credentials (D17).
# Ingest zone: reads what to fetch and stores posts; nothing else.
check_sql vb-db-ingestor ingest "read subscriptions" allowed <<SQL
SELECT count(*) FROM subscriptions;
SQL
check_sql vb-db-ingestor ingest "insert a post twice (idempotent)" allowed <<SQL
$INSERT_POST
$INSERT_POST
SQL
check_sql vb-db-ingestor ingest "read summaries" denied <<SQL
SELECT count(*) FROM summaries;
SQL
check_sql vb-db-ingestor ingest "write post_sentiments" denied <<SQL
INSERT INTO post_sentiments (post_uri, label, model) VALUES ('$POST_URI', 'neutral', 'test');
SQL
check_sql vb-db-ingestor ingest "delete subscriptions" denied <<SQL
DELETE FROM subscriptions WHERE kind = 'handle' AND value = '$SUB_VALUE';
SQL
check_sql vb-db-ingestor ingest "create table" denied <<SQL
CREATE TABLE verify_boundary (id integer);
SQL
# Analysis zone: manages subscriptions, reads posts, writes summaries.
check_sql vb-db-analysis analysis "read posts and links" allowed <<SQL
SELECT count(*) FROM posts;
SELECT count(*) FROM subscription_posts;
SQL
# Identity column and RETURNING, as the API will subscribe; the upsert runs
# twice so both its insert and its update paths are exercised.
check_sql vb-db-analysis analysis "subscribe, then write its summary twice" allowed <<SQL
INSERT INTO subscriptions (kind, value) VALUES ('handle', '$SUB_VALUE') RETURNING id;
$UPSERT_SUMMARY
$UPSERT_SUMMARY
SQL
check_sql vb-db-analysis analysis "insert posts" denied <<SQL
$INSERT_POST
SQL
check_sql vb-db-analysis analysis "create table" denied <<SQL
CREATE TABLE verify_boundary (id integer);
SQL

# The whole data flow, each step as the role that will run it. Only the
# superuser can switch roles, so this one runs inside postgres-0.
run_sql postgres-0 data -U postgres -d "$DB_NAME" <<SQL
-- The API subscribes.
SET LOCAL ROLE analysis;
INSERT INTO subscriptions (kind, value) VALUES ('handle', '$SUB_VALUE') RETURNING id AS sub_id \gset
-- The ingestor stores a post and links it to the subscription.
SET LOCAL ROLE ingestor;
$INSERT_POST
INSERT INTO subscription_posts (subscription_id, post_uri) VALUES (:sub_id, '$POST_URI')
  ON CONFLICT DO NOTHING;
-- The worker classifies the post and writes the summary.
SET LOCAL ROLE analysis;
INSERT INTO post_sentiments (post_uri, label, model) VALUES ('$POST_URI', 'neutral', 'test');
$UPSERT_SUMMARY
-- The API unsubscribes: the link and the summary must go, the post stays.
DELETE FROM subscriptions WHERE id = :sub_id;
SELECT NOT EXISTS (SELECT FROM subscription_posts WHERE subscription_id = :sub_id)
   AND NOT EXISTS (SELECT FROM summaries WHERE subscription_id = :sub_id)
   AND EXISTS (SELECT FROM post_sentiments WHERE post_uri = '$POST_URI') AS cascaded \gset
\if :cascaded
\else
  DO \$\$ BEGIN RAISE EXCEPTION 'unsubscribing did not cascade as expected'; END \$\$;
\endif
SQL
report_sql lifecycle data "subscribe, ingest, summarise, unsubscribe" allowed

echo
if [ "$failures" -eq 0 ]; then
  echo "Boundary verified: $checks/$checks checks passed."
else
  echo "Boundary NOT verified: $failures of $checks checks failed." >&2
  exit 1
fi
