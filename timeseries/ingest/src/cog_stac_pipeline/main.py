import json
import os

from osgeo import gdal

from . import fs_utils, package, stac_builder
from .config import PipelineConfig
from .dataset_metadata import DatasetSpec, load_dataset_spec
from .manifest import load_input_manifest, validate_manifest_variables
from .preflight import SourceInfo, inspect_source, validate_sources


class PreflightError(ValueError):
    """Raised with every problem found before any output is written."""


def run_pipeline(config: PipelineConfig) -> None:
    configure_gdal()
    manifest = load_input_manifest(config.input_manifest_path)
    dataset_id = manifest.dataset_id
    spec = load_dataset_spec(config.dataset_file_path(dataset_id), dataset_id)

    output_dir = config.output_dir.rstrip("/")
    lookup_path = os.path.join(output_dir, "lookup.json")
    facts_path = os.path.join(output_dir, "dataset-facts.json")

    errors = []
    if os.path.basename(output_dir) != dataset_id:
        errors.append(
            f"OUTPUT_DIR must end in the dataset ID '{dataset_id}', because "
            f"lookup.json paths start with it: {config.output_dir}"
        )
    errors.extend(
        validate_manifest_variables(
            manifest, spec.variable_ids, config.require_all_variables
        )
    )
    sources = [inspect_source(variable) for variable in manifest.variables]
    errors.extend(validate_sources(spec, sources))
    previous_facts = package.read_json(facts_path)
    if previous_facts is not None:
        errors.extend(package.facts_conflicts(previous_facts, spec, sources[0]))
    if errors:
        details = "\n".join(f"  - {error}" for error in errors)
        raise PreflightError(f"Preflight failed for {dataset_id}:\n{details}")

    print_plan(spec, sources, output_dir, previous_facts)
    if config.preflight_only:
        print("\nPREFLIGHT_ONLY is set; nothing was written.")
        return

    root_cogs_dir = os.path.join(output_dir, "cogs")
    stac_dir = os.path.join(output_dir, "stac")
    fs_utils.makedirs(root_cogs_dir)
    fs_utils.makedirs(stac_dir)

    catalog = stac_builder.load_or_create_catalog(
        stac_dir, f"STAC catalog for the {dataset_id} dataset."
    )
    lookup_updates = {}
    variable_facts = {}

    for variable in manifest.variables:
        print(f"\nProcessing variable: {variable.id}")
        cogs_var_dir = os.path.join(root_cogs_dir, variable.id)
        fs_utils.makedirs(cogs_var_dir)

        collection = stac_builder.build_collection(variable.id, spec.start)
        stac_builder.process_variable(
            paths=stac_builder.VariablePaths(
                input_path=variable.uri,
                cogs_var_dir=cogs_var_dir,
                partial_path_base=os.path.join(dataset_id, "cogs", variable.id),
                var_name=variable.id,
            ),
            stac_collection=collection,
            lookup_dict=lookup_updates,
            window=config.max_bands_per_slice,
            trunc=manifest.trunc_to_uint16,
            start_dt=spec.start,
            time_delta=spec.step_delta,
        )
        collection.update_extent_from_items()
        stac_builder.replace_child(catalog, collection)
        variable_facts[variable.id] = {
            "min": float(collection.extra_fields["titiler:min"]),
            "max": float(collection.extra_fields["titiler:max"]),
            "source": variable.uri,
        }

    print("\nSaving STAC Catalog")
    stac_builder.save_catalog(catalog, stac_dir)

    print("Saving lookup dictionary")
    lookup = package.merge_variables(package.read_json(lookup_path), lookup_updates)
    fs_utils.write_text(lookup_path, json.dumps(lookup, indent=2))

    print("Saving observed dataset facts")
    facts = package.build_facts(spec, sources[0], previous_facts, variable_facts)
    fs_utils.write_text(facts_path, json.dumps(facts, indent=2) + "\n")

    print("\nDone!")
    print(f"  STAC catalog: {stac_dir}")
    print(f"  COG slices:   {root_cogs_dir}")
    print(f"  Lookup dict:  {lookup_path}")
    print(f"  Facts:        {facts_path}")
    print(
        "To publish, place this package in a data release and set `release:` in "
        "deploy/metadata/<environment>.yml to that release."
    )


def print_plan(
    spec: DatasetSpec,
    sources: list[SourceInfo],
    output_dir: str,
    previous_facts: dict | None,
) -> None:
    resolution = spec.time_delta or "single timestep"
    print(
        f"Preflight passed for {spec.dataset_id}: {spec.gte} to {spec.lte} "
        f"({resolution}), {spec.expected_band_count} timesteps"
    )
    for source in sources:
        print(
            f"  {source.variable_id}: {source.band_count} bands, {source.crs} "
            f"<- {source.uri}"
        )
    state = "updating existing package" if previous_facts else "new package"
    print(f"Output: {output_dir} ({state})")


def configure_gdal() -> None:
    gdal.UseExceptions()
    gdal.SetCacheMax(4608 * 1024 * 1024)  # 4.5 GB
    gdal.SetConfigOption("GDAL_NUM_THREADS", "ALL_CPUS")


def main() -> None:
    run_pipeline(PipelineConfig.from_env())


if __name__ == "__main__":
    main()
