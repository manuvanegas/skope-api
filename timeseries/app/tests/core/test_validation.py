import math
import pytest
from shapely.geometry import box

from app.core.validation import (
    estimate_cell_count,
    is_geographic,
    validate_dataset_and_variable,
    validate_geom_size,
)


# ---------------------------------------------------------------------------
# validate_dataset_and_variable

def test_validate_dataset_and_variable_happy_path(minimal_registry):
    validate_dataset_and_variable(minimal_registry, "valid-ds", "ppt")  # no exception


def test_validate_dataset_and_variable_unknown_dataset(minimal_registry):
    with pytest.raises(ValueError, match="does-not-exist"):
        validate_dataset_and_variable(minimal_registry, "does-not-exist", "ppt")


def test_validate_dataset_and_variable_unknown_variable(minimal_registry):
    with pytest.raises(ValueError, match="no-such-var"):
        validate_dataset_and_variable(minimal_registry, "valid-ds", "no-such-var")


# ---------------------------------------------------------------------------
# is_geographic

def test_is_geographic_known_epsg_4326():
    assert is_geographic(4326, [0.008, 0.0, -114.0, 0.0, -0.008, 43.0]) is True


def test_is_geographic_known_epsg_4269():
    assert is_geographic(4269, [0.008, 0.0, -114.0, 0.0, -0.008, 43.0]) is True


def test_is_geographic_utm_epsg_32612_projected():
    # origin_x = abs(200000) > 180 → False
    assert is_geographic(32612, [800.0, 0.0, 200000.0, 0.0, -800.0, 4800000.0]) is False


def test_is_geographic_unknown_epsg_heuristic_passes():
    # pixel_w=0.008 < 0.1, origin_x=114 <= 180, origin_y=43 <= 90 → True
    assert is_geographic(99999, [0.008, 0.0, -114.0, 0.0, -0.008, 43.0]) is True


def test_is_geographic_unknown_epsg_large_pixel_fails():
    # pixel_w=1000 >= 0.1 → False
    assert is_geographic(99999, [1000.0, 0.0, -114.0, 0.0, -1000.0, 43.0]) is False


def test_is_geographic_unknown_epsg_large_origin_x_fails():
    # origin_x = abs(200000) > 180 → False
    assert is_geographic(99999, [0.008, 0.0, 200000.0, 0.0, -0.008, 43.0]) is False


# ---------------------------------------------------------------------------
# estimate_cell_count

def test_estimate_cell_count_geographic():
    # 1° × 1° box, 0.00833° pixels, EPSG:4326
    bounds = (-110.0, 37.0, -109.0, 38.0)
    transform = [0.00833, 0.0, -115.0, 0.0, -0.00833, 43.0]
    result = estimate_cell_count(bounds, transform, 4326)
    expected = math.ceil(1.0 / 0.00833) * math.ceil(1.0 / 0.00833)
    assert result == expected


def test_estimate_cell_count_projected_converts_degrees_to_meters():
    # 1° × 1° in degrees, projected raster with 800m pixels, mid-lat ~37.5°
    bounds = (-110.0, 37.0, -109.0, 38.0)
    transform = [800.0, 0.0, 200000.0, 0.0, -800.0, 4800000.0]
    result = estimate_cell_count(bounds, transform, 32612)
    mid_lat = (37.0 + 38.0) / 2
    m_per_deg_lon = 111320 * math.cos(math.radians(mid_lat))
    width_m = 1.0 * m_per_deg_lon
    height_m = 1.0 * 111320
    expected = math.ceil(width_m / 800.0) * math.ceil(height_m / 800.0)
    assert result == expected


def test_estimate_cell_count_zero_area():
    # Degenerate point bbox — produces 0 cells, no exception
    bounds = (0.0, 0.0, 0.0, 0.0)
    transform = [0.00833, 0.0, -115.0, 0.0, -0.00833, 43.0]
    result = estimate_cell_count(bounds, transform, 4326)
    assert result == 0


# ---------------------------------------------------------------------------
# validate_geom_size

def test_validate_geom_size_within_limit(small_polygon_shape):
    dataset_entry = {
        "crs": "EPSG:4326",
        "transform": [0.00833, 0.0, -115.0, 0.0, -0.00833, 43.0],
    }
    validate_geom_size([small_polygon_shape], dataset_entry, max_cells=500_000)


def test_validate_geom_size_exceeds_limit(large_polygon_shape):
    dataset_entry = {
        "crs": "EPSG:4326",
        "transform": [0.00833, 0.0, -115.0, 0.0, -0.00833, 43.0],
    }
    with pytest.raises(ValueError, match="too large"):
        validate_geom_size([large_polygon_shape], dataset_entry, max_cells=500_000)


def test_validate_geom_size_multiple_shapes_uses_unary_union():
    # Two small polygons placed far apart: unary_union bbox spans a large area
    shape1 = box(-114.1, 37.9, -114.0, 38.0)
    shape2 = box(-80.1, 29.9, -80.0, 30.0)
    dataset_entry = {
        "crs": "EPSG:4326",
        "transform": [0.00833, 0.0, -115.0, 0.0, -0.00833, 43.0],
    }
    with pytest.raises(ValueError):
        validate_geom_size([shape1, shape2], dataset_entry, max_cells=10)
