-include config.mk # use a minus (-) so Make doesn't crash if it's missing

DOCKER_SHARE_MOUNT=img_logs

# Set the default ENVIRONMENT to dev if it hasn't been set by config.mk or the CLI
ENVIRONMENT ?= dev

.PHONY: help init build deploy ingest

# Make 'help' the default target if someone just types `make`
.DEFAULT_GOAL := help

help:   ##- Instructions for using this Makefile.
	@echo "usage: make [target] ..."
	@echo "Run 'make init' first to generate your local config.mk file."
	@echo "targets:"
	@sed -e '/#\{2\}-/!d; s/\\$$//; s/:[^#\t]*/:/; s/#\{2\}- *//' $(MAKEFILE_LIST)

# Target to physically create the config.mk file
config.mk:
	@echo "Generating default config.mk..."
	@echo "ENVIRONMENT=dev" > config.mk
	@echo "# Change to 'staging' or 'prod' for remote deployment" >> config.mk

init: config.mk ##- Initialize the local workspace with default configuration files
	@echo "Initialized config.mk. You can edit it now, or just run 'make deploy'."

build: deploy/compose/base.yml deploy/compose/$(ENVIRONMENT).yml deploy/Dockerfile
	@echo "Building for ENVIRONMENT: $(ENVIRONMENT)"
	case "$(ENVIRONMENT)" in \
	  dev|staging|prod) docker compose -f deploy/compose/base.yml -f "deploy/compose/$(ENVIRONMENT).yml" --project-directory . config > docker-compose.yml;; \
	  *) echo "invalid environment. must be dev, staging, or prod" 1>&2; exit 1;; \
	esac
	docker compose build --pull

deploy: build   ##- build and deploy the web app 
	mkdir -p $(DOCKER_SHARE_MOUNT)
	docker compose up -d

ingest: ##- Build and run the COG/STAC ingest pipeline container
	docker compose --profile ingest build ingest
	docker compose --profile ingest run --rm ingest

##
## Testing
##

.PHONY: test

test: 	##- Run python unit tests
	docker compose run --rm server pytest
