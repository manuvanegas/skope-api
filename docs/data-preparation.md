# Dataset Preparation Runbook

This runbook prepares the dataset tree mounted at `/data` by the API and
TiTiler. Development uses `./cog-input`; staging and production use
`/srv/datasets`. Preparing data and deploying the API are separate operations:
build and validate data outside the live dataset directory, then promote it.

The canonical processor is the containerized COG/STAC pipeline in
`timeseries/ingest`. The older scripts in
[`openskope/skope-datasets`](https://github.com/openskope/skope-datasets) are
useful provenance, but target the retired `/projects/skope/datasets` layout and
do not generate the `lookup.json` required by the current API.

## Required dataset contract

Each published dataset has this shape beneath the mounted storage root:

```text
<storage-root>/
└── <dataset_id>/
    ├── lookup.json
    ├── cogs/
    │   └── <variable_id>/
    │       └── <variable_id>_<slice>.tif
    └── stac/
        └── catalog.json
```

`lookup.json` maps each variable and ordered ISO timestep to a COG path and
one-based band index. Its paths are relative to `<storage-root>`, for example:

```json
{
  "ppt_annual": {
    "0103": {
      "file": "paleocar_v3/cogs/ppt_annual/ppt_annual_1.tif",
      "bidx": 1
    }
  }
}
```

The dataset ID and variable IDs must exactly match the registry used by the
target environment. Keep these files aligned:

- `timeseries/ingest/metadata.yml`, used to validate pipeline inputs
- `timeseries/metadata.yml`, mounted as the development API registry
- `deploy/metadata/staging.yml` and `deploy/metadata/prod.yml`, built into the
  deployed API images

Do not promote output when an input filename, lookup key, or registry variable
ID differs.

## Prepare PaleoCAR v3 source files

The public source is the [`skope` S3 website](http://skope.s3-website-us-west-2.amazonaws.com/).
The bucket contains twelve PaleoCAR v3 variable groups. Each group contains
`prediction.tif`, `prediction_scaled.tif`, `pi_deviation.tif`, and
`pi_deviation_scaled.tif`; individual files are roughly 1.2–2.9 GB.

Planning issue
[`openskope/planning#40`](https://github.com/openskope/planning/issues/40)
defines the target ingest set as the `prediction_scaled.tif` product from these
nine variable groups:

| Pipeline variable ID | Public S3 object |
| --- | --- |
| `gdd_cotton_annual` | `paleocar_v3/gdd_cotton_annual/prediction_scaled.tif` |
| `gdd_cotton_maysept` | `paleocar_v3/gdd_cotton_maysept/prediction_scaled.tif` |
| `gdd_maize_annual` | `paleocar_v3/gdd_maize_annual/prediction_scaled.tif` |
| `gdd_maize_wateryear` | `paleocar_v3/gdd_maize_wateryear/prediction_scaled.tif` |
| `gdd_wheat_annual` | `paleocar_v3/gdd_wheat_annual/prediction_scaled.tif` |
| `gdd_wheat_maysept` | `paleocar_v3/gdd_wheat_maysept/prediction_scaled.tif` |
| `ppt_annual` | `paleocar_v3/ppt_annual/prediction_scaled.tif` |
| `ppt_maysept` | `paleocar_v3/ppt_maysept/prediction_scaled.tif` |
| `ppt_wateryear` | `paleocar_v3/ppt_wateryear/prediction_scaled.tif` |

The bucket also exposes `gdd_cotton_wateryear`, `gdd_maize_maysept`, and
`gdd_wheat_wateryear`, but issue #40 does not include them. Add them only after
the intended public-variable scope and metadata have been confirmed.

Before downloading, resolve the current registry mismatch. The checked-in
ingest metadata describes four annual scaled and unscaled variables, while
staging and production advertise four older variable IDs. Update the ingest
metadata and all applicable API registries to the nine IDs above. The commands
below implement issue #40 and must not be used for deployment until that
metadata change is complete.

From the `skope-api` repository root, download each selected source into the
flat input directory and name it after its pipeline variable ID:

```bash
mkdir -p cog-input

for variable_id in \
  gdd_cotton_annual \
  gdd_cotton_maysept \
  gdd_maize_annual \
  gdd_maize_wateryear \
  gdd_wheat_annual \
  gdd_wheat_maysept \
  ppt_annual \
  ppt_maysept \
  ppt_wateryear
do
  curl --fail --location --continue-at - \
    --output "cog-input/${variable_id}.tif" \
    "https://skope.s3.us-west-2.amazonaws.com/paleocar_v3/${variable_id}/prediction_scaled.tif"
done
```

Record the checksums in the release record after downloading. S3 multipart
ETags are not MD5 checksums, so calculate local SHA-256 values:

```bash
sha256sum cog-input/*.tif
```

## Run the pipeline

The checked-in Compose profile configures PaleoCAR v3 as annual data beginning
in 0103 CE, slices each input into COGs of at most 100 bands, converts values to
UInt16, and writes output under `timeseries/ingest/output/paleocar_v3`:

```bash
make ingest
```

The pipeline validates spatial and temporal metadata, creates COG slices and a
self-contained STAC catalog, and generates `lookup.json`. Existing COG slices
are skipped, so an interrupted run can be resumed. Remove or isolate stale
output before intentionally changing input data or ingest parameters; skipped
files are not rebuilt automatically.

## Validate generated output

Run the ingest tests and check the generated package before promotion:

```bash
make test-ingest
python -m json.tool timeseries/ingest/output/paleocar_v3/lookup.json >/dev/null
test -s timeseries/ingest/output/paleocar_v3/stac/catalog.json
find timeseries/ingest/output/paleocar_v3/cogs -type f -name '*.tif'
```

Also verify that:

1. Every intended registry variable occurs in `lookup.json`, and no unexpected
   variable is present.
2. Each variable begins at `0103`, ends at `2000`, and has ordered annual keys.
3. Every lookup file exists beneath the generated storage root and every band
   index is valid.
4. `gdalinfo` reports the expected CRS, transform, extent, data type, nodata
   value, tiling, compression, and band count for representative first and last
   slices.
5. Metadata changes made by the pipeline are reviewed and deliberately copied
   into all applicable API registries.

For an end-to-end development check, copy the generated dataset package—not
the raw source TIFFs—into the local storage root, deploy development, and test
metadata, a representative tile, and a small extraction:

```bash
rsync -a timeseries/ingest/output/paleocar_v3/ cog-input/paleocar_v3/
make deploy-dev
curl --fail --show-error http://127.0.0.1:8001/metadata
```

## Promote to staging and production

Promotion must preserve the validated directory exactly. Record the source
commit, pipeline configuration, source URLs, SHA-256 checksums, output size,
and processing date with the release.

1. Copy the generated `<dataset_id>` directory to a temporary, versioned path
   on the target host, outside live `/srv/datasets/<dataset_id>`.
2. Repeat the lookup, COG, STAC, and `gdalinfo` checks against that copy.
3. Retain the current dataset directory as the rollback copy.
4. Use the host provisioning/release procedure to atomically make the validated
   directory available as `/srv/datasets/<dataset_id>` with read permission for
   the API and TiTiler containers.
5. Deploy the matching API registry using the
   [deployment runbook](deployment.md), then test metadata, a representative
   tile, and a small extraction through the public hostname.
6. Promote the same validated artifact to production; do not rerun the pipeline
   independently for production.

If verification fails, restore the previous dataset directory and redeploy the
matching previous API commit. Dataset files and API registry versions must be
rolled back together.

Exact host copy and atomic-switch commands are intentionally delegated to
`comses/infrastructure`; this repository does not define filesystem ownership,
release-directory naming, or whether staging and production share storage.
