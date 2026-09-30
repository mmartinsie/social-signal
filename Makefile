# SocialSignal: entry points to build, run and verify the system.
#
# Portability: this file must work with GNU make 3.81 (the macOS default) and
# BSD userland. Do not use .ONESHELL or .SHELLFLAGS (make >= 3.82), nor
# GNU-only flags such as `sed -i` without a suffix, `readlink -f` or `date -d`.

.DEFAULT_GOAL := help

# Targets are implemented step by step. Until then they fail loudly so that a
# placeholder is never mistaken for a working step. $(1) = planned step.
not_implemented = echo "make $@: not implemented yet (planned in step $(1), see docs/PROGRESS.md)" >&2; exit 1

.PHONY: help build start stop clean verify-boundary

help: ## List the available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Install dependencies and build all container images
	@$(call not_implemented,5)

start: ## Create the local cluster and deploy the system
	@$(call not_implemented,3)

stop: ## Stop the running system
	@$(call not_implemented,3)

clean: ## Remove the local cluster and build artefacts
	@$(call not_implemented,3)

verify-boundary: ## Prove that the analysis zone cannot reach the internet
	@$(call not_implemented,3)
