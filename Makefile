ENVIRONMENT ?= dev
COMPOSE_PROJECT_NAME ?= skope-api
LEGACY_DATA_ROOT ?= /srv/datasets/skope
MIGRATED_DATA_ROOT ?= timeseries/ingest/output/legacy-migration
MIGRATION_SCRATCH_ROOT ?= timeseries/ingest/output/legacy-migration-scratch
# Each environment's data release is the unquoted path after `release:` in
# deploy/metadata/<environment>.yml, so the deployed commit determines both the
# registry and the data mounted at /data. Command-line values are ignored on purpose.
override DATASET_RELEASE_ROOT = $(shell sed -n 's/^release:[[:space:]]*//p' deploy/metadata/$(ENVIRONMENT).yml | sed 's/[[:space:]]*\#.*//')
export DATASET_RELEASE_ROOT
COMPOSE = docker compose --project-name $(COMPOSE_PROJECT_NAME) \
	--project-directory . \
	-f deploy/compose/base.yml \
	-f deploy/compose/$(ENVIRONMENT).yml
TEST_COMPOSE = docker compose --project-name $(COMPOSE_PROJECT_NAME)-test \
	--project-directory . \
	-f deploy/compose/base.yml \
	-f deploy/compose/dev.yml

.PHONY: help check-environment collect-release-facts prepare config build deploy \
	deploy-dev deploy-staging deploy-production down restart logs ps ingest \
	migrate-legacy-data test test-api test-ingest

# Make 'help' the default target if someone just types `make`
.DEFAULT_GOAL := help

help:   ##- Instructions for using this Makefile.
	@echo "usage: make [target] ..."
	@echo "targets:"
	@sed -e '/#\{2\}-/!d; s/\\$$//; s/:[^#\t]*/:/; s/#\{2\}- *//' $(MAKEFILE_LIST)

check-environment:
	@case "$(ENVIRONMENT)" in \
	  dev|staging|prod) ;; \
	  *) echo "ENVIRONMENT must be dev, staging, or prod (got '$(ENVIRONMENT)')" 1>&2; exit 2;; \
	esac

prepare: check-environment
	@if [ "$(ENVIRONMENT)" = dev ]; then mkdir -p cog-input timeseries/ingest/output; fi

# Copies the selected release's <dataset_id>/dataset-facts.json files into the build context,
# where the image build merges them into the registry.
collect-release-facts: check-environment
	@if [ -z "$(DATASET_RELEASE_ROOT)" ]; then \
	  echo "Set release: in deploy/metadata/$(ENVIRONMENT).yml to the data release to deploy" 1>&2; \
	  exit 2; \
	fi
	@if [ "$(ENVIRONMENT)" != dev ] && { [ ! -d "$(DATASET_RELEASE_ROOT)" ] || [ ! -r "$(DATASET_RELEASE_ROOT)" ]; }; then \
	  echo "The release in deploy/metadata/$(ENVIRONMENT).yml is not a readable directory: $(DATASET_RELEASE_ROOT)" 1>&2; \
	  exit 2; \
	fi
	@rm -rf build/release-facts && mkdir -p build/release-facts
	@for facts in "$(DATASET_RELEASE_ROOT)"/*/dataset-facts.json; do \
	  [ -f "$$facts" ] || continue; \
	  cp "$$facts" "build/release-facts/$$(basename "$$(dirname "$$facts")").json"; \
	done

config: check-environment ##- Render and validate the selected Compose configuration
	@$(COMPOSE) config

build: prepare collect-release-facts ##- Build the selected environment's images
	@$(COMPOSE) config --quiet
	$(COMPOSE) build --pull

deploy: build ##- Deploy ENVIRONMENT (defaults to dev) and wait for healthy services
	$(COMPOSE) up -d --remove-orphans --force-recreate --wait --wait-timeout 120

deploy-dev: override ENVIRONMENT=dev
deploy-dev: deploy ##- Build and deploy the local development environment

deploy-staging: override ENVIRONMENT=staging
deploy-staging: deploy ##- Build and deploy staging on its application host

deploy-production: override ENVIRONMENT=prod
deploy-production: deploy ##- Build and deploy production on its application host

down: check-environment ##- Stop and remove the selected environment's containers
	$(COMPOSE) down

restart: check-environment ##- Restart the selected environment's services
	$(COMPOSE) restart

logs: check-environment ##- Follow logs for the selected environment
	$(COMPOSE) logs --follow --tail=200

ps: check-environment ##- Show service status for the selected environment
	$(COMPOSE) ps

ingest: prepare ##- Build and run the local COG/STAC ingest pipeline container
	$(COMPOSE) --profile ingest build ingest
	$(COMPOSE) --profile ingest run --rm ingest

migrate-legacy-data: ##- Transform legacy cubes into COG/STAC/lookup dataset packages
	./scripts/migrate-legacy-datasets.sh \
		"$(LEGACY_DATA_ROOT)" \
		"$(MIGRATED_DATA_ROOT)" \
		"$(MIGRATION_SCRATCH_ROOT)"

##
## Testing
##

.PHONY: test

test: test-api test-ingest ##- Run all API and ingest tests

test-api: override ENVIRONMENT=dev
test-api: prepare collect-release-facts ##- Build the development image and run the API tests
	@$(TEST_COMPOSE) config --quiet
	$(TEST_COMPOSE) build server titiler
	@trap '$(TEST_COMPOSE) down --remove-orphans' EXIT INT TERM; \
		$(TEST_COMPOSE) run --rm server sh -c \
		'black --check app && pytest -c app/pytest.ini app/tests'

test-ingest: override ENVIRONMENT=dev
test-ingest: prepare ##- Build and run the ingest tests
	@$(TEST_COMPOSE) --profile test config --quiet
	$(TEST_COMPOSE) --profile test build ingest-test
	@trap '$(TEST_COMPOSE) --profile test down --remove-orphans' EXIT INT TERM; \
		$(TEST_COMPOSE) --profile test run --rm --no-deps ingest-test
