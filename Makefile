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

CLUSTER         := socialsignal
KUBE_CONTEXT    := k3d-$(CLUSTER)
K3D_CONFIG      := deploy/k3d/cluster.yaml
PLATFORM_DIR    := deploy/platform

HELM_RELEASE    := socialsignal
HELM_CHART      := deploy/helm/socialsignal
# Only the release metadata lives here; every resource sets its own namespace.
HELM_NAMESPACE  := default

# Everything the scripts need, passed explicitly as environment variables.
SCRIPT_ENV = K3S_VERSION='$(K3S_VERSION)' K3S_IMAGE='$(K3S_IMAGE)' \
  K3D_PROXY_IMAGE='$(K3D_PROXY_IMAGE)' K3D_TOOLS_IMAGE='$(K3D_TOOLS_IMAGE)' \
  CURL_IMAGE='$(CURL_IMAGE)' \
  NODE_IMAGES='$(NODE_IMAGES)' WORKLOAD_IMAGES='$(WORKLOAD_IMAGES)' \
  IMAGES_DIR='$(IMAGES_DIR)' ARCH='$(ARCH)' \
  CLUSTER='$(CLUSTER)' KUBE_CONTEXT='$(KUBE_CONTEXT)' \
  K3D_CONFIG='$(K3D_CONFIG)' PLATFORM_DIR='$(PLATFORM_DIR)'

.PHONY: help build images start stop clean distclean verify-boundary

help: ## List the available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: images ## Install dependencies and build all container images

images: ## Download every third-party image into the offline bundle
	@$(SCRIPT_ENV) sh scripts/bundle-images.sh

start: ## Start the local cluster from the offline bundle and deploy the system
	@$(SCRIPT_ENV) sh scripts/cluster-up.sh
	helm upgrade --install $(HELM_RELEASE) $(HELM_CHART) \
	  --kube-context $(KUBE_CONTEXT) --namespace $(HELM_NAMESPACE) --wait --timeout 10m

stop: ## Stop the local cluster, keeping its state
	k3d cluster stop $(CLUSTER)

clean: ## Delete the local cluster (the image bundle in dist/ is kept)
	k3d cluster delete $(CLUSTER)

distclean: clean ## Delete the local cluster and the image bundle
	rm -rf dist

verify-boundary: ## Prove that the analysis zone cannot reach the internet
	@$(SCRIPT_ENV) sh scripts/verify-boundary.sh
