#!/bin/sh
# Zero-downtime demos against the running cluster (D26):
#
#   ha-demo.sh update   replace every API pod, as `make start` does when the
#                       API image changes (a rolling update)
#   ha-demo.sh drain    drain a node that runs an API pod, as before node
#                       maintenance, then make it schedulable again
#
# Meanwhile a client on this host asks the JSON API for the summaries,
# through Traefik like an analyst's browser, several times per second. At
# the end it prints how many requests failed, and exits 1 if any did.
#
# The drain never picks PostgreSQL's node: it is a single instance (D14), so
# moving it is an outage by design. Whatever happens, the drained node is
# uncordoned on exit.
#
# Inputs (environment, set by the Makefile): KUBE_CONTEXT, APP_RELEASE
#   DEMO_URL  optional, default http://localhost:8088/api/subscriptions
#
# POSIX sh on purpose: it must run with both Linux and macOS userland.

set -eu

: "${KUBE_CONTEXT:?}" "${APP_RELEASE:?}"
kubectl="kubectl --context $KUBE_CONTEXT"
URL=${DEMO_URL:-http://localhost:8088/api/subscriptions}
API_PODS="app.kubernetes.io/component=api,app.kubernetes.io/instance=$APP_RELEASE"

mode=${1:-}
case "$mode" in
  update | drain) ;;
  *)
    echo "usage: $0 update|drain" >&2
    exit 2
    ;;
esac

log=$(mktemp "${TMPDIR:-/tmp}/socialsignal-demo.XXXXXX")
load_pid=""
drained=""

cleanup() {
  if [ -n "$load_pid" ]; then kill "$load_pid" 2>/dev/null || true; fi
  if [ -n "$drained" ]; then
    $kubectl uncordon "$drained" >/dev/null 2>&1 || true
    echo "Uncordoned $drained."
  fi
  rm -f "$log"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

fail() {
  echo "$*" >&2
  exit 1
}

api_pods() {
  $kubectl -n analysis get pods -l "$API_PODS" \
    -o jsonpath='{range .items[*]}  {.metadata.name} on {.spec.nodeName}{"\n"}{end}'
}

# One line per request: seconds since the start, and the HTTP status (000:
# no answer at all).
start_load() {
  (
    start=$(date +%s)
    while :; do
      code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$URL" || true)
      echo "$(($(date +%s) - start)) $code"
      sleep 0.1
    done
  ) >"$log" 2>/dev/null &
  load_pid=$!
  # Some traffic before the disruption, to compare with.
  sleep 5
}

stop_load() {
  # Keep the load on until every old pod is gone: a pod still in its
  # graceful shutdown is exactly when requests could fail.
  replicas=$($kubectl -n analysis get deployment api -o jsonpath='{.spec.replicas}')
  tries=0
  while [ "$($kubectl -n analysis get pods -l "$API_PODS" -o name | wc -l)" -gt "$replicas" ]; do
    tries=$((tries + 1))
    [ "$tries" -le 120 ] || fail "Old API pods were still terminating after 2 minutes."
    sleep 1
  done
  # And some more traffic once everything has settled.
  sleep 5
  kill "$load_pid" 2>/dev/null || true
  load_pid=""
}

report() {
  total=$(wc -l <"$log")
  ok=$(grep -c ' 200$' "$log" || true)
  failed=$((total - ok))
  last=$(tail -n 1 "$log" | cut -d' ' -f1)
  echo
  echo "Requests during the demo: $total over ${last}s; answered 200: $ok; failed: $failed."
  if [ "$failed" -ne 0 ]; then
    echo "Failed requests, per second of the demo (count, second, status):" >&2
    grep -v ' 200$' "$log" | uniq -c >&2
    exit 1
  fi
  echo "No request failed: zero downtime."
}

code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$URL" || true)
[ "$code" = 200 ] || fail "$URL answered '$code', not 200: is the system running (make start)?"

echo "API pods before:"
api_pods

if [ "$mode" = update ]; then
  echo
  echo "Rolling update of the API under load (one new pod ready before an old one stops)..."
  start_load
  $kubectl -n analysis rollout restart deployment/api >/dev/null
  $kubectl -n analysis rollout status deployment/api --timeout=300s
  stop_load
else
  db_node=$($kubectl -n data get pod postgres-0 -o jsonpath='{.spec.nodeName}')
  node=$($kubectl -n analysis get pods -l "$API_PODS" -o jsonpath='{range .items[*]}{.spec.nodeName}{"\n"}{end}' |
    grep -v -x "$db_node" | head -n 1 || true)
  [ -n "$node" ] || fail "Every API pod runs on PostgreSQL's node ($db_node); nothing to drain safely."
  echo
  echo "Draining $node under load (PostgreSQL is on $db_node and is not moved). Pods on it:"
  $kubectl get pods -A --field-selector "spec.nodeName=$node,status.phase=Running" \
    -o custom-columns='  NAMESPACE:.metadata.namespace,POD:.metadata.name' --no-headers
  start_load
  drained=$node
  # Evictions respect the PodDisruptionBudgets: an API, Traefik or CoreDNS
  # pod only leaves while another one is ready.
  $kubectl drain "$node" --ignore-daemonsets --delete-emptydir-data --timeout=300s
  $kubectl -n analysis rollout status deployment/api --timeout=300s
  stop_load
  $kubectl uncordon "$node" >/dev/null
  drained=""
  echo "Uncordoned $node."
fi

echo
echo "API pods after:"
api_pods
report
