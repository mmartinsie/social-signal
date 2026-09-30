#!/bin/sh
# Build the project's own images and add them to the offline bundle, under
# $IMAGES_DIR/<arch>/app/. Each image is tagged with a hash of its content,
# the first 12 hex digits of its image ID (D15): the tag changes if and only
# if the image changes. That is what makes `make start` roll out new code,
# because the cluster cannot pull and uses IfNotPresent. The references are
# written to $IMAGES_DIR/<arch>/app/images.txt, which `make start` reads.
#
# Inputs (environment, set by the Makefile):
#   IMAGES_DIR, PYTHON_IMAGE, UV_IMAGE
#   APP_IMAGES  space-separated name:package:directory entries
#   ARCH        optional: amd64 or arm64 (default: the Docker host's)
#
# POSIX sh on purpose: it must run with both Linux and macOS userland.

set -eu
. "$(dirname "$0")/lib.sh"

: "${IMAGES_DIR:?}" "${PYTHON_IMAGE:?}" "${UV_IMAGE:?}" "${APP_IMAGES:?}"

ARCH=$(detect_arch)
native=$(ARCH='' detect_arch)
if [ "$ARCH" != "$native" ]; then
  echo "warning: building linux/$ARCH images on a $native host needs QEMU emulation (binfmt)." >&2
fi

app_dir="$IMAGES_DIR/$ARCH/app"
mkdir -p "$app_dir"
iid_file=$(mktemp "${TMPDIR:-/tmp}/socialsignal-iid.XXXXXX")
list_file="$app_dir/images.txt.part"
trap 'rm -f "$iid_file" "$list_file"' EXIT
: >"$list_file"

echo "Application images for linux/$ARCH in $app_dir"
for entry in $APP_IMAGES; do
  IFS=: read -r name package directory <<EOF
$entry
EOF
  repository="socialsignal/$name"
  echo "build $repository ($package)"
  # No provenance/SBOM attestations: BuildKit stores them in the image index
  # with per-build metadata, so the ID (and our tag) would change on every
  # build even when the image itself is identical.
  docker build --quiet --platform "linux/$ARCH" --iidfile "$iid_file" \
    --provenance=false --sbom=false \
    -f docker/python-service.Dockerfile \
    --build-arg PYTHON_IMAGE="$PYTHON_IMAGE" --build-arg UV_IMAGE="$UV_IMAGE" \
    --build-arg PACKAGE="$package" --build-arg SERVICE_DIR="$directory" \
    . >/dev/null
  image_id=$(cat "$iid_file")
  tag=$(printf '%s' "${image_id#sha256:}" | cut -c1-12)
  reference="$repository:$tag"
  docker tag "$image_id" "$reference"

  file=$(image_tarball "$app_dir" "$reference")
  if [ -f "$file" ]; then
    echo "ok    $reference (unchanged, already in the bundle)"
  else
    # Replace the tarball of any previous build of this image.
    prefix=$(printf '%s' "$repository" | tr '/:' '__')
    for old in "$app_dir/${prefix}_"*.tar; do
      if [ -f "$old" ]; then rm -f "$old"; fi
    done
    docker save --platform "linux/$ARCH" -o "$file.part" "$reference"
    mv "$file.part" "$file"
    echo "ok    $reference (new build)"
  fi
  echo "$name=$reference" >>"$list_file"
done

revision=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
{
  echo "# Built on $(date -u '+%Y-%m-%dT%H:%M:%SZ') from git revision $revision."
  cat "$list_file"
} >"$app_dir/images.txt"
