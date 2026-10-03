#!/bin/sh
# Stop the local k3d cluster, keeping its state (D28). Before stopping, it
# suspends the CronJobs, so no run starts while the cluster goes down or
# while it comes back and PostgreSQL is still recovering. `make start`
# resumes them once the database and the application are ready (deploy.sh).
#
# Inputs (environment, set by the Makefile): CLUSTER, KUBE_CONTEXT
# POSIX sh on purpose: it must run with both Linux and macOS userland.

set -eu

: "${CLUSTER:?}" "${KUBE_CONTEXT:?}"
kubectl="kubectl --context $KUBE_CONTEXT --request-timeout=10s"

if ! k3d cluster get "$CLUSTER" >/dev/null 2>&1; then
  echo "No cluster $CLUSTER: nothing to stop."
  exit 0
fi

# --- 1. Suspend the CronJobs (skipped if the cluster is already down) -------
if $kubectl get namespace ingest >/dev/null 2>&1; then
  for ns in ingest analysis; do
    for cronjob in $($kubectl -n "$ns" get cronjob -o name); do
      $kubectl -n "$ns" patch "$cronjob" --type=merge -p '{"spec":{"suspend":true}}' >/dev/null
      echo "pause $ns/${cronjob#*/}"
    done
  done
else
  echo "note  the cluster API does not answer: CronJobs left as they are"
fi

# --- 2. Stop the nodes -------------------------------------------------------
k3d cluster stop "$CLUSTER"

echo
echo "Cluster $CLUSTER stopped; its data is kept. Start it again with 'make start'."
# On WSL2, Linux keeps the files it read cached, and Windows still counts
# that memory as the VM's (Vmmem) until Linux lets it go.
if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "WSL2: to give the cached memory back to Windows now, run:"
  echo "  sync && sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'"
fi
