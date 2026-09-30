# SocialSignal: entry points to build, run and verify the system.
#
# Portability: this file must work with GNU make 3.81 (the macOS default) and
# BSD userland. Do not use .ONESHELL or .SHELLFLAGS (make >= 3.82), nor
# GNU-only flags such as `sed -i` without a suffix, `readlink -f` or `date -d`.

.DEFAULT_GOAL := help

# Pinned third-party images. `make build` saves them as tarballs under
# $(IMAGES_DIR)/<arch>/ so `make start` never pulls from a registry
# (see D4 in docs/DECISIONS.md).
K3S_VERSION     := v1.36.4+k3s1
K3S_IMAGE       := rancher/k3s:$(subst +,-,$(K3S_VERSION))
K3D_HELPER_TAG  := 5.9.0
K3D_PROXY_IMAGE := ghcr.io/k3d-io/k3d-proxy:$(K3D_HELPER_TAG)
K3D_TOOLS_IMAGE := ghcr.io/k3d-io/k3d-tools:$(K3D_HELPER_TAG)
CURL_IMAGE      := curlimages/curl:8.22.0

NODE_IMAGES     := $(K3S_IMAGE) $(K3D_PROXY_IMAGE) $(K3D_TOOLS_IMAGE)
WORKLOAD_IMAGES := $(CURL_IMAGE)

IMAGES_DIR      := dist/images
# Empty means the Docker host's architecture; override with ARCH=amd64|arm64.
ARCH            ?=

# Targets are implemented step by step. Until then they fail loudly so that a
# placeholder is never mistaken for a working step. $(1) = planned step.
not_implemented = echo "make $@: not implemented yet (planned in step $(1), see docs/PROGRESS.md)" >&2; exit 1

.PHONY: help build images start stop clean verify-boundary

help: ## List the available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: images ## Install dependencies and build all container images

images: ## Download every third-party image into the offline bundle
	@K3S_VERSION='$(K3S_VERSION)' NODE_IMAGES='$(NODE_IMAGES)' \
	  WORKLOAD_IMAGES='$(WORKLOAD_IMAGES)' IMAGES_DIR='$(IMAGES_DIR)' ARCH='$(ARCH)' \
	  sh scripts/bundle-images.sh

start: ## Create the local cluster and deploy the system
	@$(call not_implemented,3)

stop: ## Stop the running system
	@$(call not_implemented,3)

clean: ## Remove the local cluster and build artefacts
	@$(call not_implemented,3)

verify-boundary: ## Prove that the analysis zone cannot reach the internet
	@$(call not_implemented,3)
