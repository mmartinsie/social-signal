#!/bin/sh
# Build the offline image bundle: every third-party image the cluster needs is
# saved as a tarball under $IMAGES_DIR/<arch>/, so `make start` never pulls
# from a registry. Only this script needs internet access (Docker Hub, GHCR
# and GitHub releases); the resulting directory can be carried to a host whose
# only outbound access is Bluesky.
#
# Layout of $IMAGES_DIR/<arch>/:
#   k3s/       k3s air-gap images (CoreDNS, Traefik, pause...), mounted into
#              every node; k3s imports them when it starts.
#   node/      images k3d runs as Docker containers; loaded with `docker load`.
#   workload/  images for our pods; imported with `k3d image import`.
#
# Inputs (environment, set by the Makefile):
#   K3S_VERSION      k3s release, e.g. v1.36.4+k3s1
#   NODE_IMAGES      space-separated image references
#   WORKLOAD_IMAGES  space-separated image references
#   IMAGES_DIR       output directory, e.g. dist/images
#   ARCH             optional: amd64 or arm64 (default: the Docker host's)
#
# POSIX sh on purpose: it must run with both Linux and macOS userland.

set -eu
. "$(dirname "$0")/lib.sh"

: "${K3S_VERSION:?}" "${NODE_IMAGES:?}" "${WORKLOAD_IMAGES:?}" "${IMAGES_DIR:?}"

ARCH=$(detect_arch)
bundle="$IMAGES_DIR/$ARCH"
echo "Offline image bundle for linux/$ARCH in $bundle"

# --- k3s air-gap images, verified against the release's official checksums ---
k3s_dir="$bundle/k3s"
airgap="k3s-airgap-images-$ARCH.tar.zst"
# The checksum file lives outside k3s/ so k3s never sees it.
sums="$bundle/k3s-sha256sum-$ARCH.txt"
release_url="https://github.com/k3s-io/k3s/releases/download/$(printf '%s' "$K3S_VERSION" | sed 's/+/%2B/')"

airgap_ok() {
  [ -f "$k3s_dir/$airgap" ] && [ -f "$sums" ] || return 1
  expected=$(awk -v f="$airgap" '$2 == f { print $1 }' "$sums")
  actual=$(shasum -a 256 "$k3s_dir/$airgap" | awk '{ print $1 }')
  [ -n "$expected" ] && [ "$expected" = "$actual" ]
}

mkdir -p "$k3s_dir"
if airgap_ok; then
  echo "ok    $airgap (already present, checksum verified)"
else
  echo "fetch $airgap"
  curl -fsSL -o "$sums" "$release_url/sha256sum-$ARCH.txt"
  curl -fL --progress-bar -o "$k3s_dir/$airgap" "$release_url/$airgap"
  if ! airgap_ok; then
    rm -f "$k3s_dir/$airgap"
    echo "checksum mismatch for $airgap" >&2
    exit 1
  fi
  echo "ok    $airgap (checksum verified)"
fi

# --- Container images, one tarball per image and platform ---
save_images() { # $1 = subdirectory, remaining arguments = image references
  dir="$bundle/$1"
  shift
  mkdir -p "$dir"
  for image in "$@"; do
    file=$(image_tarball "$dir" "$image")
    if [ -f "$file" ]; then
      echo "ok    $image (already saved)"
      continue
    fi
    echo "pull  $image"
    docker pull --quiet --platform "linux/$ARCH" "$image" >/dev/null
    # Write to a temporary name first so an interrupted save is never
    # mistaken for a complete tarball on the next run.
    docker save --platform "linux/$ARCH" -o "$file.part" "$image"
    mv "$file.part" "$file"
    echo "ok    $image"
  done
}

# The lists are space-separated on purpose, so word splitting is intended.
# shellcheck disable=SC2086
save_images node $NODE_IMAGES
# shellcheck disable=SC2086
save_images workload $WORKLOAD_IMAGES

echo "Bundle size: $(du -sh "$bundle" | awk '{ print $1 }')"
