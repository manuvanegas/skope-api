import math
from typing import Sequence

from shapely.ops import unary_union
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry.base import BaseGeometry
from pyproj import CRS

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

def estimate_cell_count(geom_bounds: Sequence[float], transform: Sequence[float], epsg_str: str) -> int:
    """
    Estimates the number of cells that would be processed for a given geometry and dataset resolution.
    """    
    minx, miny, maxx, maxy = geom_bounds

    if CRS.from_string(epsg_str).is_geographic:
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
    if all(isinstance(s, ShapelyPoint) for s in shapes):
        return  # A point is exactly 1 cell — always within limits
    geom_bounds = unary_union(shapes).bounds
    transform = dataset_entry["transform"]
    estimated_cells = estimate_cell_count(geom_bounds, transform, dataset_entry["crs"])

    if estimated_cells > max_cells:
        raise ValueError(f"Selected area is too large. Estimated cell count: {estimated_cells}, maximum allowed: {max_cells}.")