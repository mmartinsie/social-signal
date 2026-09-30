#!/bin/sh
# Download the LLM weights into $MODELS_DIR (A1, D22), pinned to a Hugging
# Face repository revision and verified against the file's sha256. Only
# `make build` downloads them; they are baked into the LLM image, so nothing
# is fetched at runtime. Safe to re-run: a verified file is kept, and an
# interrupted download resumes where it stopped.
#
# Inputs (environment, set by the Makefile):
#   MODELS_DIR, MODEL_REPO, MODEL_REVISION, MODEL_FILE, MODEL_SHA256
#
# POSIX sh on purpose: it must run with both Linux and macOS userland.

set -eu

: "${MODELS_DIR:?}" "${MODEL_REPO:?}" "${MODEL_REVISION:?}" "${MODEL_FILE:?}" "${MODEL_SHA256:?}"

target="$MODELS_DIR/$MODEL_FILE"
part="$target.part"
url="https://huggingface.co/$MODEL_REPO/resolve/$MODEL_REVISION/$MODEL_FILE"

sha256_ok() { # file
  [ "$(shasum -a 256 "$1" | awk '{ print $1 }')" = "$MODEL_SHA256" ]
}

mkdir -p "$MODELS_DIR"
if [ -f "$target" ]; then
  echo "check $MODEL_FILE (sha256 of a multi-GB file takes a moment)"
  if sha256_ok "$target"; then
    echo "ok    $MODEL_FILE (already present, checksum verified)"
    exit 0
  fi
  echo "checksum mismatch for the existing $MODEL_FILE: downloading it again" >&2
  rm -f "$target"
fi

echo "fetch $MODEL_REPO@$MODEL_REVISION $MODEL_FILE"
# -C -: resume a previous partial download.
downloaded=true
curl -fL --retry 3 --progress-bar -C - -o "$part" "$url" || downloaded=false

if sha256_ok "$part"; then
  mv "$part" "$target"
  echo "ok    $MODEL_FILE (checksum verified)"
elif [ "$downloaded" = false ]; then
  echo "Download of $MODEL_FILE interrupted; run 'make build' again to resume." >&2
  exit 1
else
  rm -f "$part"
  echo "checksum mismatch for $MODEL_FILE: the download was deleted." >&2
  exit 1
fi
