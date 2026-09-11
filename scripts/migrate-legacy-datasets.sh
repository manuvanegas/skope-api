#!/bin/sh
set -eu

if [ "$#" -ne 3 ]; then
    echo "usage: $0 LEGACY_DATA_ROOT MIGRATED_DATA_ROOT MIGRATION_SCRATCH_ROOT" >&2
    exit 2
fi

legacy_data_root=$1
migrated_data_root=$2
migration_scratch_root=$3
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_root=$(dirname -- "$script_dir")

if [ ! -d "$legacy_data_root/datasets" ]; then
    echo "legacy dataset directory not found: $legacy_data_root/datasets" >&2
    exit 2
fi

if [ -e "$migrated_data_root" ] && [ -n "$(find "$migrated_data_root" -mindepth 1 -print -quit)" ]; then
    echo "migration output must be absent or empty: $migrated_data_root" >&2
    exit 2
fi

required_inputs='
datasets/lbda_v2/pmdi/cube.tif
datasets/paleocar_v2/gdd_may_sept/cube.tif
datasets/paleocar_v2/maize_farming_niche/cube.tif
datasets/paleocar_v2/ppt_water_year/cube.tif
datasets/prism/ppt/cube.tif
datasets/prism/tmax/cube.tif
datasets/prism/tmin/cube.tif
datasets/srtm/srtm_elevation/cube.tif
'

echo "$required_inputs" | while IFS= read -r relative_path; do
    [ -z "$relative_path" ] && continue
    if [ ! -r "$legacy_data_root/$relative_path" ]; then
        echo "required legacy input is missing or unreadable: $legacy_data_root/$relative_path" >&2
        exit 2
    fi
done

mkdir -p "$migrated_data_root/_migration"
mkdir -p "$migration_scratch_root"
legacy_data_root=$(CDPATH= cd -- "$legacy_data_root" && pwd)
migrated_data_root=$(CDPATH= cd -- "$migrated_data_root" && pwd)
migration_scratch_root=$(CDPATH= cd -- "$migration_scratch_root" && pwd)
# Record the exact inputs used, as release provenance.
cp -R "$repository_root/timeseries/ingest/manifests" \
    "$repository_root/deploy/metadata/datasets" \
    "$migrated_data_root/_migration/"

compose() {
    docker compose \
        --project-name skope-api-migration \
        --project-directory "$repository_root" \
        -f "$repository_root/deploy/compose/base.yml" \
        -f "$repository_root/deploy/compose/dev.yml" \
        "$@"
}

# Timespans come from deploy/metadata/datasets/<id>.yml and UInt16 conversion from
# each manifest; every described variable must be migrated.
run_dataset() {
    dataset_id=$1
    manifest_path=$2

    echo "Migrating $dataset_id"
    compose --profile ingest run --rm --no-deps \
        -e "INPUT_MANIFEST_PATH=$manifest_path" \
        -e "OUTPUT_DIR=/output/$dataset_id" \
        -e REQUIRE_ALL_VARIABLES=true \
        -e TMPDIR=/scratch \
        -v "$legacy_data_root:/legacy:ro" \
        -v "$migrated_data_root:/output" \
        -v "$migration_scratch_root:/scratch" \
        ingest
}

compose --profile ingest build ingest

run_dataset lbda_v2 /ingest/manifests/legacy/lbda_v2.yml
run_dataset paleocar_v2 /ingest/manifests/legacy/paleocar_v2.yml
run_dataset paleocar_v3 /ingest/manifests/paleocar_v3.yml
run_dataset prism /ingest/manifests/legacy/prism.yml
run_dataset srtm /ingest/manifests/legacy/srtm.yml

echo "Migration complete: $migrated_data_root"
echo "To deploy it, set 'release: $migrated_data_root' in deploy/metadata/staging.yml."
