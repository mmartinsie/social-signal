#!/bin/sh
# Create the database credentials as Kubernetes Secrets, outside Helm (D13).
# The passwords are random, generated here on the target, and never stored in
# the repository, the image bundle or a Helm release. Each zone only gets its
# own role:
#   data/postgres-credentials  every password (PostgreSQL's init script needs them)
#   data/db-migrator           migrator (migration Job, step 4b)
#   ingest/db-ingestor         ingestor
#   analysis/db-analysis       analysis
# Idempotent: existing Secrets are kept. It refuses to invent new passwords
# for a database volume that already exists, because its roles were created
# with the old ones. Passwords only travel through stdin, never argv.
#
# Inputs (environment, set by the Makefile): KUBE_CONTEXT
# POSIX sh on purpose: it must run with both Linux and macOS userland.

set -eu

: "${KUBE_CONTEXT:?}"
kubectl="kubectl --context $KUBE_CONTEXT"

MASTER_NS=data
MASTER=postgres-credentials
# volumeClaimTemplate "data" of StatefulSet "postgres", pod 0.
DB_VOLUME=data-postgres-0

fail() {
  echo "$*" >&2
  exit 1
}

secret_exists() { # namespace name
  $kubectl get secret "$2" -n "$1" >/dev/null 2>&1
}

secret_value() { # namespace name key -> decoded value, empty if missing
  # A failing template makes kubectl print the whole object, Secret data
  # included (D27): `with` keeps a missing key from failing it.
  $kubectl get secret "$2" -n "$1" -o go-template="{{with index .data \"$3\"}}{{base64decode .}}{{end}}"
}

new_password() {
  LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32
}

# --- Master Secret with every password --------------------------------------
fresh=false
if secret_exists "$MASTER_NS" "$MASTER"; then
  echo "ok    secret $MASTER_NS/$MASTER (kept)"
else
  if $kubectl get pvc "$DB_VOLUME" -n "$MASTER_NS" >/dev/null 2>&1; then
    fail "Secret $MASTER_NS/$MASTER is missing but the database volume $DB_VOLUME exists:
new passwords would not match the roles stored in it. Restore the Secret, or
delete the cluster and its data with 'make clean'."
  fi
  echo "new   secret $MASTER_NS/$MASTER"
  $kubectl create -f - >/dev/null <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: $MASTER
  namespace: $MASTER_NS
  labels:
    app.kubernetes.io/part-of: socialsignal
    app.kubernetes.io/managed-by: make-start
type: Opaque
stringData:
  postgres-password: "$(new_password)"
  migrator-password: "$(new_password)"
  ingestor-password: "$(new_password)"
  analysis-password: "$(new_password)"
EOF
  fresh=true
fi

# --- One Secret per zone, with only that zone's role ------------------------
role_secret() { # namespace name role
  if [ "$fresh" = false ] && secret_exists "$1" "$2"; then
    echo "ok    secret $1/$2 (kept)"
    return
  fi
  password=$(secret_value "$MASTER_NS" "$MASTER" "$3-password")
  [ -n "$password" ] || fail "No $3-password in $MASTER_NS/$MASTER."
  # A new master means new passwords: replace any stale copy.
  $kubectl delete secret "$2" -n "$1" --ignore-not-found >/dev/null
  echo "new   secret $1/$2"
  $kubectl create -f - >/dev/null <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: $2
  namespace: $1
  labels:
    app.kubernetes.io/part-of: socialsignal
    app.kubernetes.io/managed-by: make-start
type: Opaque
stringData:
  username: "$3"
  password: "$password"
EOF
}

role_secret data db-migrator migrator
role_secret ingest db-ingestor ingestor
role_secret analysis db-analysis analysis
