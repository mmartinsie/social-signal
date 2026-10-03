#!/bin/sh
# Install or upgrade the two Helm releases, the database first (D2): the
# application's migration hook runs before any of its resources, so it needs
# PostgreSQL to exist already. The application images come from the bundle's
# images.txt, written by `make build`.
#
# Inputs (environment, set by the Makefile):
#   KUBE_CONTEXT, IMAGES_DIR, ARCH (optional)
#   DB_RELEASE, DB_CHART, DB_NAMESPACE, POSTGRES_IMAGE
#   APP_RELEASE, APP_CHART, APP_NAMESPACE
#
# POSIX sh on purpose: it must run with both Linux and macOS userland.

set -eu
. "$(dirname "$0")/lib.sh"

: "${KUBE_CONTEXT:?}" "${IMAGES_DIR:?}"
: "${DB_RELEASE:?}" "${DB_CHART:?}" "${DB_NAMESPACE:?}" "${POSTGRES_IMAGE:?}"
: "${APP_RELEASE:?}" "${APP_CHART:?}" "${APP_NAMESPACE:?}"

ARCH=$(detect_arch)
images="$IMAGES_DIR/$ARCH/app/images.txt"
if [ ! -f "$images" ]; then
  echo "No application images for linux/$ARCH ($images): run 'make build' first." >&2
  exit 1
fi

# One --set images.<name>=<reference> per line of images.txt.
set --
while IFS='=' read -r name reference; do
  case "$name" in
    '' | '#'*) continue ;;
  esac
  set -- "$@" --set "images.$name=$reference"
done <"$images"

helm upgrade --install "$DB_RELEASE" "$DB_CHART" \
  --kube-context "$KUBE_CONTEXT" --namespace "$DB_NAMESPACE" \
  --set "image=$POSTGRES_IMAGE" --wait --timeout 10m

helm upgrade --install "$APP_RELEASE" "$APP_CHART" \
  --kube-context "$KUBE_CONTEXT" --namespace "$APP_NAMESPACE" \
  "$@" --wait --timeout 10m

# `make stop` suspends the CronJobs (D28): resume them now that the database
# and the application are ready. The chart leaves `suspend` out on purpose:
# Helm 4 applies server-side and would refuse to take the field back.
for ns in ingest analysis; do
  for cronjob in $(kubectl --context "$KUBE_CONTEXT" -n "$ns" get cronjob -o name); do
    if [ "$(kubectl --context "$KUBE_CONTEXT" -n "$ns" get "$cronjob" -o jsonpath='{.spec.suspend}')" = true ]; then
      kubectl --context "$KUBE_CONTEXT" -n "$ns" patch "$cronjob" --type=merge -p '{"spec":{"suspend":false}}' >/dev/null
      echo "resume $ns/${cronjob#*/}"
    fi
  done
done
