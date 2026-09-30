# Shared helpers for the scripts in this directory. Source it, don't run it.
# POSIX sh on purpose: it must work with both Linux and macOS userland.

# detect_arch: print amd64 or arm64. Honours $ARCH when it is set; otherwise
# asks the Docker daemon, so the bundle matches the host the cluster runs on.
detect_arch() {
  arch="${ARCH:-}"
  if [ -z "$arch" ]; then
    case "$(docker info --format '{{.Architecture}}')" in
      x86_64 | amd64) arch=amd64 ;;
      aarch64 | arm64) arch=arm64 ;;
      *) echo "unsupported Docker architecture; set ARCH=amd64 or ARCH=arm64" >&2; return 1 ;;
    esac
  fi
  case "$arch" in
    amd64 | arm64) echo "$arch" ;;
    *) echo "ARCH must be amd64 or arm64, got '$arch'" >&2; return 1 ;;
  esac
}

# image_tarball DIR IMAGE: path of the tarball that holds IMAGE inside DIR.
image_tarball() {
  printf '%s/%s.tar' "$1" "$(printf '%s' "$2" | tr '/:' '__')"
}
