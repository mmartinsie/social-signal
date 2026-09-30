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
POSTGRES_IMAGE  := postgres:18.6-alpine3.23

NODE_IMAGES     := $(K3S_IMAGE) $(K3D_PROXY_IMAGE) $(K3D_TOOLS_IMAGE)
WORKLOAD_IMAGES := $(CURL_IMAGE) $(POSTGRES_IMAGE)

# Our own images: built by `make build` from one Dockerfile, tagged by content
# (D15). Base images are only needed at build time, not in the bundle.
PYTHON_IMAGE    := python:3.12.14-slim-trixie
UV_IMAGE        := ghcr.io/astral-sh/uv:0.12.21
# name:package:directory
APP_IMAGES      := migrations:socialsignal-migrations:services/migrations

IMAGES_DIR      := dist/images
# Empty means the Docker host's architecture; override with ARCH=amd64|arm64.
ARCH            ?=

CLUSTER         := socialsignal
KUBE_CONTEXT    := k3d-$(CLUSTER)
K3D_CONFIG      := deploy/k3d/cluster.yaml
PLATFORM_DIR    := deploy/platform

# Two Helm releases with separate lifecycles (D2): the database first, so the
# application's migration hook always finds it.
DB_RELEASE      := socialsignal-db
DB_CHART        := deploy/helm/socialsignal-db
DB_NAMESPACE    := data
APP_RELEASE     := socialsignal
APP_CHART       := deploy/helm/socialsignal
# Only the release metadata lives here; every resource sets its own namespace.
APP_NAMESPACE   := default

# Everything the scripts need, passed explicitly as environment variables.
SCRIPT_ENV = K3S_VERSION='$(K3S_VERSION)' K3S_IMAGE='$(K3S_IMAGE)' \
  K3D_PROXY_IMAGE='$(K3D_PROXY_IMAGE)' K3D_TOOLS_IMAGE='$(K3D_TOOLS_IMAGE)' \
  CURL_IMAGE='$(CURL_IMAGE)' \
  NODE_IMAGES='$(NODE_IMAGES)' WORKLOAD_IMAGES='$(WORKLOAD_IMAGES)' \
  IMAGES_DIR='$(IMAGES_DIR)' ARCH='$(ARCH)' \
  CLUSTER='$(CLUSTER)' KUBE_CONTEXT='$(KUBE_CONTEXT)' \
  K3D_CONFIG='$(K3D_CONFIG)' PLATFORM_DIR='$(PLATFORM_DIR)' \
  PYTHON_IMAGE='$(PYTHON_IMAGE)' UV_IMAGE='$(UV_IMAGE)' APP_IMAGES='$(APP_IMAGES)' \
  POSTGRES_IMAGE='$(POSTGRES_IMAGE)' \
  DB_RELEASE='$(DB_RELEASE)' DB_CHART='$(DB_CHART)' DB_NAMESPACE='$(DB_NAMESPACE)' \
  APP_RELEASE='$(APP_RELEASE)' APP_CHART='$(APP_CHART)' APP_NAMESPACE='$(APP_NAMESPACE)'

.PHONY: help build images app-images start stop clean distclean verify-boundary

help: ## List the available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: images app-images ## Install dependencies and build all container images

images: ## Download every third-party image into the offline bundle
	@$(SCRIPT_ENV) sh scripts/bundle-images.sh

app-images: ## Build our own images and add them to the offline bundle
	@$(SCRIPT_ENV) sh scripts/build-images.sh

start: ## Start the local cluster from the offline bundle and deploy the system
	@$(SCRIPT_ENV) sh scripts/cluster-up.sh
	@$(SCRIPT_ENV) sh scripts/db-secrets.sh
	@$(SCRIPT_ENV) sh scripts/deploy.sh

stop: ## Stop the local cluster, keeping its state
	k3d cluster stop $(CLUSTER)

clean: ## Delete the local cluster (the image bundle in dist/ is kept)
	k3d cluster delete $(CLUSTER)

distclean: clean ## Delete the local cluster and the image bundle
	rm -rf dist

verify-boundary: ## Prove the network boundary and the database privileges
	@$(SCRIPT_ENV) sh scripts/verify-boundary.sh
