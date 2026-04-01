import math
from typing import Sequence

from shapely.ops import unary_union
from shapely.geometry.base import BaseGeometry

# ---------------------------------------------------------------------------
# Dataset and variable validation to prevent arbitrary or malicious queries

def validate_dataset_and_variable(registry: dict, dataset_id: str, variable_id: str) -> None:
    """
    Validates dataset and variable existence to prevent arbitrary or malicious queries.
    Raises ValueError if the IDs are not found in the registry.
    """
    dataset = registry.get(dataset_id)
    if not dataset:
        raise ValueError(f"Dataset '{dataset_id}' not found.")
        
    variables = dataset.get("variables", [])

    if not any(var.get("id") == variable_id for var in variables):
        raise ValueError(f"Variable '{variable_id}' not found in dataset '{dataset_id}'.")
    

# ---------------------------------------------------------------------------
# Geometry size validation to prevent excessively large queries

COMMON_GEOGRAPHIC_EPSG = {
    4326, 4322, 4269, 4267, 4258, 4277, 4674, 
    4618, 4283, 4490, 4284, 4166, 4135, 4250, 4261
}

def is_geographic(epsg_code: str, transform: list) -> bool:
    # Heuristic: Is it degrees?
    # 1. Is the EPSG known to be geographic?
    if epsg_code in COMMON_GEOGRAPHIC_EPSG:
        return True
        
    # 2. Fallback to the origin & pixel-size heuristic
    pixel_w = abs(transform[0])
    origin_x = abs(transform[2])
    origin_y = abs(transform[5])
    
    return (origin_x <= 180 and origin_y <= 90 and pixel_w < 0.1)

def estimate_cell_count(geom_bounds: Sequence[float], transform: Sequence[float], epsg_code: str) -> int:
    """
    Estimates the number of cells that would be processed for a given geometry and dataset resolution.
    """    
    minx, miny, maxx, maxy = geom_bounds

    is_geo = is_geographic(epsg_code, transform)

    if is_geo:
        width_units = maxx - minx
        height_units = maxy - miny
    else:
        # Raster in meters, Geometry in degrees
        mid_lat = (miny + maxy) / 2
        m_per_deg_lat = 111320
        m_per_deg_lon = 111320 * math.cos(math.radians(mid_lat))
        
        width_units = (maxx - minx) * m_per_deg_lon
        height_units = (maxy - miny) * m_per_deg_lat
    
    pixel_w = abs(transform[0])
    pixel_h = abs(transform[4])

    cols = math.ceil(width_units / pixel_w)
    rows = math.ceil(height_units / pixel_h)
    
    return cols * rows

def validate_geom_size(shapes: list[BaseGeometry], dataset_entry: dict, max_cells: int) -> None:
    """
    Validates that the geometry does not exceed a maximum number of cells when rasterized.
    Accepts a list of Shapely geometries and a registry dataset entry (with 'crs' and 'transform').
    Raises ValueError if the geometry is too large.
    """
    geom_bounds = unary_union(shapes).bounds
    transform = dataset_entry["transform"]
    epsg_code = int(dataset_entry["crs"].replace("EPSG:", ""))
    estimated_cells = estimate_cell_count(geom_bounds, transform, epsg_code)

    if estimated_cells > max_cells:
        raise ValueError(f"Selected area is too large. Estimated cell count: {estimated_cells}, maximum allowed: {max_cells}.")