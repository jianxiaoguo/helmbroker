# If DRYCC_REGISTRY is not set, try to populate it from legacy DEV_REGISTRY
DRYCC_REGISTRY ?= $(DEV_REGISTRY)
IMAGE_PREFIX ?= drycc-addons
COMPONENT ?= helmbroker
SHORT_NAME ?= $(COMPONENT)
PLATFORM ?= linux/amd64,linux/arm64

include versioning.mk

SHELLCHECK_PREFIX := podman run --rm -v ${CURDIR}:/workdir -w /workdir ${DEV_REGISTRY}/drycc/go-dev shellcheck
SHELL_SCRIPTS = $(wildcard rootfs/bin/*) $(shell find "rootfs" -name '*.sh') $(wildcard _scripts/*.sh)

# Test processes used in quick unit testing
TEST_PROCS ?= 4

check-kubectl:
	@if [ -z $$(which kubectl) ]; then \
	  echo "kubectl binary could not be located"; \
	  exit 2; \
	fi

check-podman:
	@if [ -z $$(which podman) ]; then \
	  echo "Missing \`podman\` client which is required for development"; \
	  exit 2; \
	fi

build: podman-build

podman-build: check-podman
	podman build ${PODMAN_BUILD_FLAGS} --build-arg CODENAME=${CODENAME} -t ${IMAGE} rootfs
	podman tag ${IMAGE} ${MUTABLE_IMAGE}

podman-build-test: check-podman
	podman build ${PODMAN_BUILD_FLAGS} --build-arg CODENAME=${CODENAME} -t ${IMAGE}.test -f rootfs/Dockerfile.test rootfs

deploy: check-kubectl podman-build podman-push
	kubectl --namespace=drycc patch deployment drycc-$(COMPONENT) --type='json' -p='[{"op": "replace", "path": "/spec/template/spec/containers/0/image", "value":"$(IMAGE)"}]'

clean: check-podman
	podman rmi $(IMAGE)

full-clean: check-podman
	podman images -q $(IMAGE_PREFIX)/$(COMPONENT) | xargs podman rmi -f

test: test-style test-unit test-functional

test-style: podman-build-test
	$(shell chown -R 1001:1001 ${CURDIR})
	podman run --rm -v ${CURDIR}:/tmp/test -w /tmp/test/rootfs ${IMAGE}.test /tmp/test/rootfs/bin/test-style
	${SHELLCHECK_PREFIX} $(SHELL_SCRIPTS)

test-unit: podman-build-test
	@echo "Implement in the future"

test-functional:
	@echo "Implement functional tests in _tests directory"

test-integration:
	@echo "Check https://github.com/drycc/workflow-e2e for the complete integration test suite"

upload-coverage:
	$(eval CI_ENV := $(shell curl -s https://codecov.io/env | bash))
	podman run --rm ${CI_ENV} -v ${CURDIR}:/tmp/test -w /tmp/test/rootfs ${IMAGE}.test /tmp/test/rootfs/bin/upload-coverage

.PHONY: check-kubectl check-podman build podman-build podman-build-test deploy clean commit-hook full-clean test test-style test-unit test-functional test-integration upload-coverage
