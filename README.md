# skope-api

[![DOI](https://zenodo.org/badge/338436138.svg)](https://zenodo.org/badge/latestdoi/338436138)
[![skope-api build](https://github.com/openskope/skope-api/actions/workflows/test.yml/badge.svg)](https://github.com/openskope/skope-api/actions/workflows/test.yml)

Backend services for dataset metadata and timeseries data extracted from SKOPE datasets - see https://api.openskope.org/docs for API details and examples

## Project Setup

### Dataset Metadata

The registry exposed by the [metadata endpoint](https://api.openskope.org/docs#/metadata/metadata_metadata_get) and consumed by the [skopeui](https://github.com/openskope/skopeui) app is generated when the API image is built, from:

- `deploy/metadata/datasets/<dataset_id>.yml`: the description of a dataset and all of its variables, one file per dataset.
- `deploy/metadata/{dev,staging,prod}.yml`: the data release the environment mounts at `/data` (`release:`) and, listed explicitly, the datasets and variables it publishes.
- `<release>/<dataset_id>/dataset-facts.json`: facts observed in the processed data (CRS, transform, timespan, per-variable min/max), written by the ingest pipeline.

The build fails with a message naming the files involved when a published variable is not described or has no processed data, an observed field appears in a dataset file, or the described and processed timespans disagree. See the [dataset preparation runbook](docs/data-preparation.md#required-dataset-contract) for how these files relate to processed data.

### Development

Build and run the API, Redis, and TiTiler locally:

```bash
make deploy-dev
```

Try out the analysis endpoint

```bash
http GET localhost:8001/docs
```

Run the tests

```bash
make test
```

### Extraction Job Durability

Extraction requests run as background tasks in the API worker that accepts them.
Redis retains job status, results, and internal analysis data for 24 hours, but it
is not an execution queue: a worker restart does not resume an in-flight job.
Clients should treat a missing job or a job that remains nonterminal across a
deployment as abandoned and submit a new extraction request.

This execution model is suitable for the current short, bounded extractions. A
separate durable worker queue is required before offering restart-safe or
resumable jobs.

## Staging and Production

See the [deployment runbook](docs/deployment.md) for preflight checks,
verification, rollback, and routine operations for all environments.
See the [dataset preparation runbook](docs/data-preparation.md) when adding or
rebuilding the contents mounted at `/data`.

The application hosts are provisioned by `comses/infrastructure`. Both environments
use `/srv/apps/skope-api` for this checkout, the data release named by `release:` in
`deploy/metadata/<environment>.yml`, and host port `8001` for the API. From the
appropriate host, deploy with:

```bash
make deploy-staging
make deploy-production
```

These targets build the selected images, start the Compose project, remove orphaned
containers, and wait for the API, Redis, and TiTiler health checks. Dataset storage
is mounted read-only at `/data` in the API and TiTiler containers. Service logs are
written to stdout and stderr for collection by Docker.

All commands also accept an explicit environment. For example:

```bash
make config ENVIRONMENT=staging
make ps ENVIRONMENT=staging
make logs ENVIRONMENT=staging
make down ENVIRONMENT=staging
```
