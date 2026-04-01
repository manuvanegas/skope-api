import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

def resolve_temporal_slice(
    lookup_data: dict,
    variable_id: str,
    start_step: str,
    end_step: str,
    base_url: str,
) -> tuple[Dict[str, List[int]], List[str]]:
    """
    Resolves a temporal window into everything needed to execute the extraction:
    a mapping of storage URIs to their band indices, and the ordered list of
    timestep strings (ISO dates) for building a time-indexed pd.Series.
    """
    var_lookup = lookup_data.get(variable_id)
    if not var_lookup:
        raise ValueError(f"Variable '{variable_id}' not found in lookup dictionary.")

    file_mapping: Dict[str, List[int]] = {}
    timestep_list: List[str] = []

    for step_str, entry in var_lookup.items():
        if step_str > end_step:
            break

        if step_str >= start_step:
            suff_uri = entry["file"]
            uri = f"{base_url.rstrip('/')}/{suff_uri}"
            band = entry["bidx"]

            if uri not in file_mapping:
                file_mapping[uri] = []
            file_mapping[uri].append(band)
            timestep_list.append(step_str)

    # Protect against internal data gaps where the slice yields no results
    if not file_mapping:
        raise ValueError("No data available within the specific requested time slice.")

    for uri in file_mapping:
        file_mapping[uri].sort()

    return file_mapping, timestep_list

def resolve_uri_single_band(lookup_data: dict, variable_id: str, timestep: str, base_url: str) -> tuple[str, int]:
    """
    Convenience function for single-year requests that need to resolve to a single file and band.
    """
    var_lookup = lookup_data.get(variable_id, {})
    
    if timestep not in var_lookup:
        logger.error(f"Year {timestep} is missing in lookup for '{variable_id}'.")
        raise ValueError(f"Year {timestep} is not available for '{variable_id}' in this dataset.")
        
    entry = var_lookup[timestep]
    suff_uri = entry["file"]
    uri = f"{base_url.rstrip('/')}/{suff_uri}"
    return uri, entry["bidx"]

