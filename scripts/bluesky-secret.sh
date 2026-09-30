#!/bin/sh
# Turn the optional Bluesky credentials in .env into the Secret
# ingest/bluesky-credentials (A6, D21). Only the hashtag ingestor mounts it;
# without it, hashtags are searched without authentication.
#   no file, or both values empty  -> the Secret is deleted, if it exists
#   only one of the two values     -> error
#   both values                    -> the Secret is created, or replaced if
#                                     the values changed
# The values only travel through shell variables, pipes and stdin, never
# through a command's arguments. Nor through `kubectl apply`, which would
# copy them in clear text into the last-applied-configuration annotation.
#
# Inputs (environment, set by the Makefile): KUBE_CONTEXT, BLUESKY_ENV_FILE
# POSIX sh on purpose: it must run with both Linux and macOS userland.

set -eu

: "${KUBE_CONTEXT:?}" "${BLUESKY_ENV_FILE:?}"
kubectl="kubectl --context $KUBE_CONTEXT"

NS=ingest
NAME=bluesky-credentials
cr=$(printf '\r')

fail() {
  echo "$*" >&2
  exit 1
}

# env_value KEY: the value of the last KEY=value line of the file, without a
# trailing carriage return (a file saved on Windows) and without one pair of
# surrounding quotes.
env_value() {
  value=""
  while IFS= read -r line || [ -n "$line" ]; do
    line=${line%"$cr"}
    case "$line" in
      "$1="*) value=${line#*=} ;;
    esac
  done <"$BLUESKY_ENV_FILE"
  case "$value" in
    \"*\" | \'*\')
      value=${value#?}
      value=${value%?}
      ;;
  esac
  printf '%s' "$value"
}

identifier=""
password=""
if [ -f "$BLUESKY_ENV_FILE" ]; then
  identifier=$(env_value BLUESKY_IDENTIFIER)
  password=$(env_value BLUESKY_APP_PASSWORD)
fi

if [ -z "$identifier" ] && [ -z "$password" ]; then
  if $kubectl get secret "$NAME" -n "$NS" >/dev/null 2>&1; then
    $kubectl delete secret "$NAME" -n "$NS" >/dev/null
    echo "del   secret $NS/$NAME (no credentials in $BLUESKY_ENV_FILE)"
  else
    echo "none  no Bluesky credentials in $BLUESKY_ENV_FILE: hashtags are searched" \
      "without authentication, which Bluesky blocks at times (see .env.example)"
  fi
  exit 0
fi
[ -n "$identifier" ] && [ -n "$password" ] ||
  fail "$BLUESKY_ENV_FILE must set both BLUESKY_IDENTIFIER and BLUESKY_APP_PASSWORD, or neither."

# base64 in `data`, rather than `stringData`, so no character in a value can
# break the YAML. Short values fit in one line; tr removes any wrapping.
identifier_b64=$(printf '%s' "$identifier" | base64 | tr -d '\n')
password_b64=$(printf '%s' "$password" | base64 | tr -d '\n')

current=$($kubectl get secret "$NAME" -n "$NS" \
  -o go-template='{{index .data "identifier"}} {{index .data "app-password"}}' 2>/dev/null) || current=""
if [ "$current" = "$identifier_b64 $password_b64" ]; then
  echo "ok    secret $NS/$NAME (kept)"
  exit 0
fi

$kubectl delete secret "$NAME" -n "$NS" --ignore-not-found >/dev/null
$kubectl create -f - >/dev/null <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: $NAME
  namespace: $NS
  labels:
    app.kubernetes.io/part-of: socialsignal
    app.kubernetes.io/managed-by: make-start
type: Opaque
data:
  identifier: $identifier_b64
  app-password: $password_b64
EOF
echo "new   secret $NS/$NAME (from $BLUESKY_ENV_FILE)"
