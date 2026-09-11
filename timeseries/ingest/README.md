# cog_stac_pipeline

Turns multi-band GeoTIFFs (one band per timestep) into a dataset package the SKOPE API serves: Cloud-Optimized GeoTIFF (COG) slices, a STAC catalog, `lookup.json`, and `dataset-facts.json`.

## What it does

A run processes one dataset. Its inputs are an **input manifest**, naming the source TIFF for each variable, and the dataset's description in `deploy/metadata/datasets/<dataset_id>.yml`, which lists the variables and declares the timespan (`gte`, `lte`, `resolution`). The pipeline reads the description and never writes it.

1. **Preflight.** Before writing anything, the pipeline reads only the source headers and checks that:
   - every manifest variable is described in the dataset file (a subset is fine unless `REQUIRE_ALL_VARIABLES` is set);
   - each source has one band per declared timestep, and band descriptions that look like timesteps run from `gte` to `lte`;
   - all sources share one EPSG CRS, transform, and size;
   - an existing package in `OUTPUT_DIR` has the same grid and timespan.

   All problems are reported together. With `PREFLIGHT_ONLY=true` the run stops here.
2. **Slices** each source into COGs of up to `MAX_BANDS_PER_SLICE` bands, efficient to serve over HTTP range requests.
3. **Builds a STAC catalog** listing every slice, its extent, time range, and raster statistics.
4. **Writes `lookup.json`**, a map from variable → ISO timestep → `{file, bidx}`, so the API can answer "give me `ppt` at year `0850`" without parsing STAC.
5. **Writes `dataset-facts.json`**, the facts observed in the data: CRS, transform, timespan, and each variable's min, max, and source. The API image build reads this file from the data release named in `deploy/metadata/<environment>.yml`.

A run updates only the variables it processes. `lookup.json`, `dataset-facts.json`, and the catalog keep variables from earlier runs, so a package can be built over several runs.

## Outputs

With `OUTPUT_DIR=/output/paleocar_v3`:

```
/output/paleocar_v3/
├── cogs/
│   └── <var>/
│       ├── <var>_1.tif   ← COG slice (bands 1–100)
│       ├── <var>_2.tif   ← COG slice (bands 101–200)
│       └── ...
├── stac/
│   ├── catalog.json
│   └── <var>/
│       ├── collection.json
│       └── <var>_1/
│           └── <var>_1.json   ← STAC Item
├── lookup.json
└── dataset-facts.json
```

**`lookup.json`:**
```json
{
  "ppt_annual": {
    "0103": { "file": "paleocar_v3/cogs/ppt_annual/ppt_annual_1.tif", "bidx": 1 },
    "0104": { "file": "paleocar_v3/cogs/ppt_annual/ppt_annual_1.tif", "bidx": 2 }
  }
}
```

**`dataset-facts.json`:**
```json
{
  "provenance": "Written by cog-stac-pipeline. ...",
  "dataset_id": "paleocar_v3",
  "crs": "EPSG:4269",
  "transform": [0.00833, 0.0, -114.9958, 0.0, -0.00833, 42.9958, 0.0, 0.0, 1.0],
  "timespan": { "resolution": { "years": 1 }, "period": { "gte": "0103", "lte": "2000" } },
  "variables": {
    "ppt_annual": { "min": 0.0, "max": 3615.0, "source": "s3://skope/paleocar_v3/ppt_annual/prediction_scaled.tif" }
  }
}
```

Paths in `lookup.json` start with the dataset ID and are relative to the directory that contains the package. That is why `OUTPUT_DIR` must end in the dataset ID.

## Input manifest

```yaml
dataset_id: paleocar_v3
trunc_to_uint16: true
variables:
  - id: ppt_annual
    uri: s3://skope/paleocar_v3/ppt_annual/prediction_scaled.tif
  - id: gdd_cotton_annual
    uri: /srv/datasets-import/paleocar_v3/gdd_cotton_annual/cube.tif
```

The URI may be a local path or an `s3://` object. The ID, not the source filename, becomes the lookup key, COG directory name, and STAC collection ID.

`trunc_to_uint16` is required. When it is true, values are cast to UInt16 with nodata 65535, and any value above 65535 becomes nodata, so use it only for data known to fit.

## Configuration

Configuration is read from environment variables by `PipelineConfig.from_env()`:

| Environment variable | Description |
|---|---|
| `INPUT_MANIFEST_PATH` | Required. The input manifest; its `dataset_id` selects the dataset file |
| `OUTPUT_DIR` | Required. Package directory; must end in the dataset ID |
| `DATASET_METADATA_DIR` | Directory of dataset files (default `datasets`). The image and `make ingest` use `/ingest/datasets`, mounted from `deploy/metadata/datasets` |
| `MAX_BANDS_PER_SLICE` | Maximum number of timesteps per COG slice (default 100) |
| `REQUIRE_ALL_VARIABLES` | Require the manifest to list every described variable (default false; the legacy migration sets it) |
| `PREFLIGHT_ONLY` | Run the checks and stop without writing anything (default false) |

## Running

From the repository root, run the checked-in PaleoCAR v3 manifest into `timeseries/ingest/output/paleocar_v3`:

```bash
make ingest
```

Dataset files and manifests are mounted read-only, so edits apply without rebuilding the image. To process a subset, put a manifest listing the variables you want in `timeseries/ingest/manifests/` and run:

```bash
docker compose --project-directory . -f deploy/compose/base.yml -f deploy/compose/dev.yml \
  --profile ingest run --rm -e INPUT_MANIFEST_PATH=/ingest/manifests/<your-manifest>.yml ingest
```

Add `-e PREFLIGHT_ONLY=true` to check the sources without writing anything.

Existing COG slices are skipped, so a run interrupted between slices resumes where it stopped. A slice that was being written when a run stopped is left incomplete: delete it before re-running. To reprocess a variable from a different source, delete its `cogs/<variable_id>/` directory first.

## S3 support ⚠️ WIP — not fully validated

Manifest URIs and `OUTPUT_DIR` accept `s3://bucket/prefix` in addition to local paths. COG reads and writes go through GDAL's `/vsis3/` virtual filesystem (converted by `fs_utils`); the STAC catalog, `lookup.json`, and `dataset-facts.json` are read and written via boto3.

Reading sources from S3 has a cost to keep in mind: the PaleoCAR v3 sources are pixel-interleaved, so each slice re-reads the whole source. That is roughly 50 GB of transfer per variable, so download the sources first for a full run.

**Known uncertainties before relying on S3 output in production:**
- `pystac.utils.make_relative_href` behavior with `s3://` URIs has not been tested; if it misbehaves, asset hrefs in all STAC items will be wrong.
- GDAL and boto3 use **separate credential chains**. An IAM role or `~/.aws/credentials` file satisfies boto3 but not necessarily GDAL; set `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` env vars (or `gdal.SetConfigOption`) to cover both.

A dry run against a small single-variable, two-band GeoTIFF on S3 is the recommended way to surface these issues before a full run.

## Prerequisites

- GDAL ≥ 3.12 (uses `gdal.Run` pipeline commands)
- Python packages managed by `uv` from `pyproject.toml`: `pystac`, `rio_stac`, `python-dateutil`, `pyyaml`
- `boto3`, only required when using S3 paths

## Module overview

| File | Responsibility |
|---|---|
| `main.py` | Orchestration: preflight, per-variable processing, saving outputs |
| `config.py` | Environment-variable configuration |
| `manifest.py` | Loading the input manifest and checking it against the described variables |
| `dataset_metadata.py` | Reading the dataset file: variable IDs, timespan, expected band count |
| `preflight.py` | Header-only source inspection and checks against the dataset file |
| `package.py` | Reading and merging `lookup.json` and `dataset-facts.json` across runs |
| `cog_builder.py` | GDAL operations: band selection → temp GeoTIFF → COG conversion |
| `stac_builder.py` | STAC item/collection/catalog creation and merging, lookup population |
| `datetime_utils.py` | ISO key formatting, date range generation, `relativedelta` helpers |
| `fs_utils.py` | Local/S3 path handling: VSI conversion, existence checks, text reads and writes |
