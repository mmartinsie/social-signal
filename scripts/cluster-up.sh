#!/bin/sh
# Start the local k3d cluster from the offline image bundle and apply the
# platform layer (namespaces and default-deny NetworkPolicies). It never pulls
# from a registry: if the bundle is missing it stops and asks for
# `make build`. Safe to re-run: it creates, starts or leaves the cluster as
# needed.
#
# Inputs (environment, set by the Makefile):
#   CLUSTER, KUBE_CONTEXT, K3D_CONFIG, PLATFORM_DIR, IMAGES_DIR
#   K3S_IMAGE, K3D_PROXY_IMAGE, K3D_TOOLS_IMAGE, NODE_IMAGES, WORKLOAD_IMAGES
#   ARCH (optional: amd64 or arm64, default: the Docker host's)
#
# POSIX sh on purpose: it must run with both Linux and macOS userland.

set -eu
. "$(dirname "$0")/lib.sh"

: "${CLUSTER:?}" "${KUBE_CONTEXT:?}" "${K3D_CONFIG:?}" "${PLATFORM_DIR:?}" "${IMAGES_DIR:?}"
: "${K3S_IMAGE:?}" "${K3D_PROXY_IMAGE:?}" "${K3D_TOOLS_IMAGE:?}" "${NODE_IMAGES:?}" "${WORKLOAD_IMAGES:?}"

ARCH=$(detect_arch)
bundle="$IMAGES_DIR/$ARCH"
kubectl="kubectl --context $KUBE_CONTEXT"

fail() {
  echo "$*" >&2
  exit 1
}

# --- 1. The bundle must be complete; nothing is ever downloaded here --------
[ -f "$bundle/k3s/k3s-airgap-images-$ARCH.tar.zst" ] ||
  fail "No image bundle for linux/$ARCH in $bundle: run 'make build' first."
for image in $NODE_IMAGES; do
  [ -f "$(image_tarball "$bundle/node" "$image")" ] || fail "Missing $image in the bundle: run 'make build'."
done
for image in $WORKLOAD_IMAGES; do
  [ -f "$(image_tarball "$bundle/workload" "$image")" ] || fail "Missing $image in the bundle: run 'make build'."
done
# Our own images, built by `make build` and tagged by content (D15).
[ -f "$bundle/app/images.txt" ] || fail "No application images in $bundle/app: run 'make build'."
APP_REFS=$(grep -v '^#' "$bundle/app/images.txt" | cut -d= -f2-)
for image in $APP_REFS; do
  [ -f "$(image_tarball "$bundle/app" "$image")" ] || fail "Missing $image in the bundle: run 'make build'."
done
# k3d needs an absolute host path for the volume mount.
bundle_abs=$(cd "$bundle" && pwd)

# --- 2. Node images: load into Docker from the bundle when missing ----------
for image in $NODE_IMAGES; do
  if docker image inspect "$image" >/dev/null 2>&1; then
    echo "ok    $image (already in Docker)"
  else
    echo "load  $image"
    docker load --quiet -i "$(image_tarball "$bundle/node" "$image")" >/dev/null
  fi
done

# --- 3. Cluster: create it, or start it if it already exists ----------------
# Pin the k3d helper images to the ones in the bundle, whatever k3d version
# the user has installed.
export K3D_IMAGE_LOADBALANCER="$K3D_PROXY_IMAGE" K3D_IMAGE_TOOLS="$K3D_TOOLS_IMAGE"
if k3d cluster get "$CLUSTER" >/dev/null 2>&1; then
  echo "start cluster $CLUSTER"
  k3d cluster start "$CLUSTER"
else
  echo "create cluster $CLUSTER"
  # k3s imports the air-gap tarball from this directory every time it starts.
  k3d cluster create "$CLUSTER" --config "$K3D_CONFIG" --image "$K3S_IMAGE" \
    --volume "$bundle_abs/k3s:/var/lib/rancher/k3s/agent/images@server:*;agent:*"
fi

# --- 4. Wait until every node is really up -----------------------------------
# After a restart Docker may give a node a new IP, and k3s then crash-loops
# for a minute or two until the Node object catches up. Require containerd
# to answer on every node and every Node to be Ready, 3 checks in a row.
nodes=$(docker ps --filter "label=k3d.cluster=$CLUSTER" --format '{{.Names}} {{.Label "k3d.role"}}' |
  awk '$2 == "server" || $2 == "agent" { print $1 }')
[ -n "$nodes" ] || fail "No running nodes found for cluster $CLUSTER."

nodes_up() {
  for node in $nodes; do
    docker exec "$node" crictl info >/dev/null 2>&1 || return 1
  done
  $kubectl wait --for=condition=Ready node --all --timeout=5s >/dev/null 2>&1
}

echo "wait  nodes ready"
tries=0
streak=0
while [ "$streak" -lt 3 ]; do
  if nodes_up; then streak=$((streak + 1)); else streak=0; fi
  tries=$((tries + 1))
  [ "$tries" -le 120 ] || fail "Nodes were not ready after 10 minutes."
  sleep 5
done

# --- 5. Workload and application images: import, then verify ----------------
in_all_nodes() { # $1 = image
  for node in $nodes; do
    docker exec "$node" crictl inspecti "$1" >/dev/null 2>&1 || return 1
  done
}

to_import=""
queue() { # directory image
  if in_all_nodes "$2"; then
    echo "ok    $2 (already in every node)"
  else
    to_import="$to_import $(image_tarball "$1" "$2")"
  fi
}
for image in $WORKLOAD_IMAGES; do queue "$bundle/workload" "$image"; done
for image in $APP_REFS; do queue "$bundle/app" "$image"; done

if [ -n "$to_import" ]; then
  echo "import$to_import"
  # The list is space-separated on purpose (paths never contain spaces).
  # shellcheck disable=SC2086
  k3d image import --cluster "$CLUSTER" $to_import
  # k3d only logs a failed import on a node and still exits 0, so check.
  for image in $WORKLOAD_IMAGES $APP_REFS; do
    in_all_nodes "$image" || fail "Import of $image failed on at least one node."
  done
  echo "ok    images present in every node"
fi

# --- 6. Wait for the system components (CoreDNS, Traefik) -------------------
# On first creation their pods wait until k3s has imported the air-gap
# tarball (pulls are blocked), which takes minutes on a slow disk.
# Traefik's Deployment only appears once k3s' Helm install job has run.
echo "wait  system components (first start can take several minutes)"
tries=0
until $kubectl -n kube-system get deployment traefik >/dev/null 2>&1; do
  tries=$((tries + 1))
  [ "$tries" -le 300 ] || fail "Traefik was not deployed after 10 minutes."
  sleep 2
done
for deployment in coredns traefik; do
  $kubectl -n kube-system rollout status "deployment/$deployment" --timeout=600s
done

# --- 7. Platform layer: namespaces and default-deny NetworkPolicies ---------
$kubectl apply -f "$PLATFORM_DIR"

echo
echo "Cluster $CLUSTER is up (kubectl context: $KUBE_CONTEXT)."
echo "Your current kubectl context was not changed; use --context $KUBE_CONTEXT."
