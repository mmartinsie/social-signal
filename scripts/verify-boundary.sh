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
# Inputs (environment, set by the Makefile): KUBE_CONTEXT, CURL_IMAGE
# POSIX sh on purpose: it must run with both Linux and macOS userland.

set -eu

: "${KUBE_CONTEXT:?}" "${CURL_IMAGE:?}"
kubectl="kubectl --context $KUBE_CONTEXT"

BLUESKY_HOST=public.api.bsky.app
BLUESKY=https://$BLUESKY_HOST/xrpc/_health
PUBLIC_IP=https://1.1.1.1
KUBE_API=https://kubernetes.default.svc
POSTGRES=postgres.data.svc:5432

# name:namespace:component, one test pod per identity. "outsider" matches no
# policy and lives in a namespace without default-deny.
PODS="vb-ingestor:ingest:ingestor vb-api:analysis:api vb-worker:analysis:worker vb-llm:analysis:llm vb-outsider:default:outsider"
TEST_LABEL=socialsignal/test=verify-boundary

delete_pods() {
  for entry in $PODS; do
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
for entry in $PODS; do
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
  printf '%-5s %-9s %-10s %-48s expected %-9s got %s\n' \
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

echo
if [ "$failures" -eq 0 ]; then
  echo "Boundary verified: $checks/$checks checks passed."
else
  echo "Boundary NOT verified: $failures of $checks checks failed." >&2
  exit 1
fi
