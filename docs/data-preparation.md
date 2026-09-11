# Dataset Preparation Runbook

This runbook prepares the dataset releases mounted at `/data` by the API and
TiTiler. Each environment mounts the release named by `release:` in
`deploy/metadata/<environment>.yml`; development defaults to `./cog-input`.
Preparing data and deploying the API are separate operations: build and
validate a new release directory, then point an environment at it in a commit.

The canonical processor is the containerized COG/STAC pipeline in
`timeseries/ingest`. The older scripts in
[`openskope/skope-datasets`](https://github.com/openskope/skope-datasets) are
useful provenance, but target the retired `/projects/skope/datasets` layout and
do not generate the `lookup.json` required by the current API.

## Required dataset contract

Each published dataset has this shape beneath the release directory:

```text
<storage-root>/
└── <dataset_id>/
    ├── lookup.json
    ├── dataset-facts.json
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

`dataset-facts.json` holds the facts the pipeline observed in the processed data:
`crs`, `transform`, `timespan`, and each variable's `min`, `max`, and source.

The API registry is built into the image from:

- `deploy/metadata/datasets/<dataset_id>.yml`, which describes the dataset and
  all of its variables, whether or not any environment publishes them. The
  pipeline reads the variable IDs and the timespan from it and never writes it.
- `deploy/metadata/<environment>.yml`, which names the release
  (`release:`) and lists, explicitly, the datasets and variables the
  environment publishes.
- The `dataset-facts.json` of each published dataset in that release, which
  `make` copies into the build.

The image build fails, naming the files involved, if a published variable is
not described or has no processed data in the release, or if the described and
processed timespans disagree. Development builds skip unprocessed data with a
warning instead.

## Prepare PaleoCAR v3 source files

The public source is the [`skope` S3 website](http://skope.s3-website-us-west-2.amazonaws.com/).
The bucket contains twelve PaleoCAR v3 variable groups. Each group contains
`prediction.tif`, `prediction_scaled.tif`, `pi_deviation.tif`, and
`pi_deviation_scaled.tif`; individual files are roughly 1.2–2.9 GB.

The checked-in manifest at
`timeseries/ingest/manifests/paleocar_v3.yml` selects the
`prediction_scaled.tif` product from all twelve variable groups:

| Pipeline variable ID | Public S3 object |
| --- | --- |
| `gdd_cotton_annual` | `paleocar_v3/gdd_cotton_annual/prediction_scaled.tif` |
| `gdd_cotton_maysept` | `paleocar_v3/gdd_cotton_maysept/prediction_scaled.tif` |
| `gdd_cotton_wateryear` | `paleocar_v3/gdd_cotton_wateryear/prediction_scaled.tif` |
| `gdd_maize_annual` | `paleocar_v3/gdd_maize_annual/prediction_scaled.tif` |
| `gdd_maize_maysept` | `paleocar_v3/gdd_maize_maysept/prediction_scaled.tif` |
| `gdd_maize_wateryear` | `paleocar_v3/gdd_maize_wateryear/prediction_scaled.tif` |
| `gdd_wheat_annual` | `paleocar_v3/gdd_wheat_annual/prediction_scaled.tif` |
| `gdd_wheat_maysept` | `paleocar_v3/gdd_wheat_maysept/prediction_scaled.tif` |
| `gdd_wheat_wateryear` | `paleocar_v3/gdd_wheat_wateryear/prediction_scaled.tif` |
| `ppt_annual` | `paleocar_v3/ppt_annual/prediction_scaled.tif` |
| `ppt_maysept` | `paleocar_v3/ppt_maysept/prediction_scaled.tif` |
| `ppt_wateryear` | `paleocar_v3/ppt_wateryear/prediction_scaled.tif` |

This extends the nine groups requested in
[`openskope/planning#40`](https://github.com/openskope/planning/issues/40) with
the three additional groups present in the bucket. The manifest is the
operational source map; `deploy/metadata/datasets/paleocar_v3.yml` describes
the dataset. A manifest may list any subset of the described variables, so a
package can be built over several runs; the legacy migration requires all of
them. The pipeline checks the manifest, the timespan, and every source's
header before it writes anything.

The default ingest profile streams these public objects directly through GDAL,
so downloading them first is not required:

```bash
make ingest
```

To transform existing production TIFFs instead, copy the manifest and replace
each `uri` with the corresponding local file path. Keep the dataset ID and use
variable IDs from the dataset file. Point `INPUT_MANIFEST_PATH` at that file
when running the container. Local and S3 sources may be mixed in one manifest.

Record the selected manifest with the release. When inputs are materialized
locally, also record SHA-256 checksums; S3 multipart ETags are not MD5 checksums:

```bash
sha256sum cog-input/*.tif
```

## Run the pipeline

The checked-in Compose profile loads the twelve-variable manifest, takes the
annual 0103–2000 timespan from `deploy/metadata/datasets/paleocar_v3.yml`,
slices each input into COGs of at most 100 bands, converts values to UInt16 as
the manifest requests, and writes output under
`timeseries/ingest/output/paleocar_v3`:

```bash
make ingest
```

Before writing anything, the pipeline reads each source's header and checks its
band count and band descriptions against the timespan, that all sources share
one grid, and that an existing package in the output directory matches. It then
creates COG slices and a self-contained STAC catalog and writes `lookup.json`
and `dataset-facts.json`, updating only the variables it processed. Add
`-e PREFLIGHT_ONLY=true` to a manual container run to stop after the checks.

Existing COG slices are skipped, so a run interrupted between slices resumes
where it stopped; delete a slice that was being written when a run stopped.
Remove or isolate stale output before intentionally changing input data or
ingest parameters; skipped files are not rebuilt automatically.

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
5. `dataset-facts.json` reports plausible values, and every variable that the target
   environment selects in `deploy/metadata/<environment>.yml` appears in both
   `lookup.json` and `dataset-facts.json`.

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

1. Assemble all generated `<dataset_id>` directories into one new release
   directory such as `/srv/dataset-releases/<release>`. Never modify a release
   once a commit names it; create a new one instead.
2. Repeat the lookup, COG, STAC, and `gdalinfo` checks against that complete
   directory.
3. In a reviewed commit, set `release:` in `deploy/metadata/staging.yml` to that
   directory, adjusting the published datasets and variables if needed.
4. Deploy that commit with `make deploy-staging` as described in the
   [deployment runbook](deployment.md), then test metadata, a representative
   tile, and a small extraction through the public hostname.
5. Promote the same validated release to production by setting `release:` in
   `deploy/metadata/prod.yml` to the same directory; do not rerun the pipeline
   independently for production.

If verification fails, redeploy the previous commit: it names the previous
release, so the data and the registry roll back together. Keep previous release
directories until no deployable commit names them.

Exact host copy and atomic-switch commands are intentionally delegated to
`comses/infrastructure`; this repository does not define filesystem ownership,
release-directory naming, or whether staging and production share storage.

## Migrate the complete legacy tree

For a legacy `/srv/datasets/skope` tree containing `datasets/lbda_v2`,
`datasets/paleocar_v2`, `datasets/prism`, and `datasets/srtm`, run:

```bash
make migrate-legacy-data \
  LEGACY_DATA_ROOT=/srv/datasets/skope \
  MIGRATED_DATA_ROOT=/srv/dataset-releases/<release> \
  MIGRATION_SCRATCH_ROOT=/srv/dataset-migration-scratch/<release>
```

The target reads legacy data without modifying it and refuses to use a
non-empty output directory. It transforms legacy cubes for LBDA v2, PaleoCAR
v2, PRISM, and SRTM, and builds the twelve-variable PaleoCAR v3 package from
the public S3 manifest. Each dataset's timespan comes from its file in
`deploy/metadata/datasets/`, and every described variable must be migrated.
Output packages, each with its `dataset-facts.json`, are written beneath
`MIGRATED_DATA_ROOT`. Large temporary TIFFs are written to the host-backed
`MIGRATION_SCRATCH_ROOT` rather than Docker's container storage.

The pipeline's preflight compares each legacy cube's band count with the
timespan in its dataset file and stops before writing anything if they
disagree. The legacy LBDA script read year `N` from band `N + 1`, so a count
mismatch there points at the cube starting at year 0 rather than at a
pipeline fault.

PRISM is migrated for completeness but is not published by any environment.
Expand `deploy/metadata/datasets/prism.yml` and select it in an environment
file before exposing it. Validate the complete generated directory using the
checks above, then set `release:` in `deploy/metadata/staging.yml` to that
exact directory. The `_migration` directory records the manifests and dataset
files used and is ignored by the API; dataset packages remain at the release
root as required by `/data/<dataset_id>/lookup.json`.
