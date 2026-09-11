# Deployment Runbook

This runbook covers the Compose-based development, staging, and production
deployments. Run every command from the repository root. Host provisioning,
DNS, TLS, and the public reverse proxy are owned by `comses/infrastructure`.

| Environment | Checkout/data location | API listener | Deploy command |
| --- | --- | --- | --- |
| Development | Local checkout; release in `deploy/metadata/dev.yml` (default `./cog-input`) | `127.0.0.1:8001` | `make deploy-dev` |
| Staging | `/srv/apps/skope-api`; release in `deploy/metadata/staging.yml` | `0.0.0.0:8001` | `make deploy-staging` |
| Production | `/srv/apps/skope-api`; release in `deploy/metadata/prod.yml` | `0.0.0.0:8001` | `make deploy-production` |

## Before deploying

1. Select the exact reviewed commit to deploy. On staging and production,
   update `/srv/apps/skope-api` to that commit using the project's release
   process and confirm that `git status --short` is empty. Do not deploy an
   unreviewed branch or a dirty checkout.
2. Confirm CI passed for that commit. Locally, run the same test suite with:

   ```bash
   make test
   ```

3. If dataset metadata changed, edit its sources under `deploy/metadata/` as
   described in "Required dataset contract" in the
   [dataset preparation runbook](data-preparation.md#required-dataset-contract).
   The image build merges them into the registry and fails on inconsistencies.
   For staging and production, confirm that the release named by `release:` in
   `deploy/metadata/<environment>.yml` exists on the host and that each
   deployed dataset has a valid `{dataset_id}/lookup.json`, a
   `{dataset_id}/dataset-facts.json`, and all referenced COGs. Follow the
   [dataset preparation runbook](data-preparation.md) to build, validate, and
   promote dataset releases.
4. Coordinate around active extraction jobs. Redis retains job state for 24
   hours, but an API worker restart abandons work executing in that worker.
   Clients must resubmit jobs that remain nonterminal across a deployment.
5. Render the selected Compose configuration before changing services:

   ```bash
   make config ENVIRONMENT=dev
   make config ENVIRONMENT=staging
   make config ENVIRONMENT=prod
   ```

   Only the command for the environment being deployed is required. Render all
   three when changing shared Compose or deployment files.

## Deploy

Each environment mounts one complete, immutable dataset release into `/data`
in both containers: the path after `release:` in
`deploy/metadata/<environment>.yml`. The image build reads that release's
`<dataset_id>/dataset-facts.json` files, so the deployed commit determines both the
registry and the data. To serve different data, change that line in a reviewed
commit; command-line overrides are ignored.

```bash
make deploy-dev
make deploy-staging
make deploy-production
```

The target builds the selected images with refreshed base images, recreates the
Compose containers, removes orphaned containers, and waits up to 120 seconds
for the API, Redis, and TiTiler health checks. It refuses a staging or
production deploy when `release:` is unset or the release is not a readable
directory. TiTiler remains on the internal Compose network; public tile
requests pass through the API.

## Verify

Set `ENVIRONMENT` to `dev`, `staging`, or `prod`, matching the deployment:

```bash
make ps ENVIRONMENT=<environment>
curl --fail --show-error http://127.0.0.1:8001/metadata
curl --fail --show-error http://127.0.0.1:8001/docs
```

All three services must report healthy, and both HTTP requests must succeed.
For staging and production, also exercise a known dataset through the public
hostname: request its metadata, one representative tile, and—when the release
affects extraction—submit and poll a small extraction. This verifies the
reverse proxy, API-to-TiTiler path, dataset mount, and Redis job path.

Follow service output when verification fails:

```bash
make logs ENVIRONMENT=<environment>
```

## Roll back

1. Record the failed commit and capture relevant logs.
2. Restore the checkout to the previous known-good commit, which names its own
   release. Confirm the checkout is clean and that release still exists.
3. Run the canonical deploy target.
4. Repeat all verification checks above.

Rollback rebuilds the images from the selected commit and remounts its release;
image tags alone are not a rollback mechanism. Treat extraction jobs interrupted by either deploy
as abandoned and resubmit them.

## Routine operations

```bash
make ps ENVIRONMENT=<environment>
make logs ENVIRONMENT=<environment>
make restart ENVIRONMENT=<environment>
make down ENVIRONMENT=<environment>
```

`restart` can interrupt active extractions. `down` stops and removes the
environment's containers and should not be part of a routine deployment.
