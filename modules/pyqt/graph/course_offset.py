"""Compatibility imports for the map geometry shared by all GUI backends."""

from modules.map.geometry import (
    direction_arrow_polygons,
    offset_points_by_segment,
    offset_polyline,
)

__all__ = ["direction_arrow_polygons", "offset_points_by_segment", "offset_polyline"]
