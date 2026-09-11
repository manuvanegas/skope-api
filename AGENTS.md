# Skope API Agent Guide

Skope API is a FastAPI service for dataset metadata, COG raster tiles, and asynchronous time-series extraction and analysis. Application code lives under `timeseries/app/`.

## Working Conventions

- Use the root Make targets; tests and services run through Docker Compose.
- The public dataset registry is generated at image build time by `python -m app.registry_build`: each dataset and all of its variables are described in `deploy/metadata/datasets/<id>.yml`; `deploy/metadata/{dev,staging,prod}.yml` names the environment's data release (`release:`) and lists explicitly the datasets and variables it publishes; observed facts come from that release's `<id>/dataset-facts.json`, written by the ingest pipeline. Edit those sources, never the generated `/code/metadata.yml`.
- Dataset storage is resolved through `{dataset_id}/lookup.json`. Every environment mounts its `release:` read-only at `/data` in both the API and TiTiler containers; releases must never change once a commit names them.
- Keep TiTiler internal. Public raster requests must pass through the API so identifiers are validated and storage paths remain private.
- Extraction is asynchronous: clients submit, poll status, then analyze. Redis job records expire after 24 hours.
- `base_series` is internal job state used by analysis and must never appear in status responses.
- Keep service logs on standard output and standard error for Docker-managed collection.
- `comses/infrastructure` owns host provisioning. `skope-terraform` is retired.

## Validation And Deployment

Run `make test` for the isolated pytest suite. Render Compose changes for `dev`, `staging`, and `prod` with `make config ENVIRONMENT=<environment>`.

Deploy only through `make deploy-dev`, `make deploy-staging`, or `make deploy-production`. Do not restore `./configure`, `config.mk`, or generated root Compose files.

## Git And Decisions

- Use Conventional Commit messages and keep commits logically scoped.
- Do not create commits unless the user explicitly asks.
- Architectural decisions live in `.agents/decisions/`. Add an ADR only for durable, cross-cutting choices; preserve accepted ADRs and supersede them with a new ADR when a decision changes.
