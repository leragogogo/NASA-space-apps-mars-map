import numpy as np
import pytest

from app.graph.hazards import HazardMasks, hazard_masks
from app.layers.contracts import PoiData, PoiFeature, PoiKind
from app.layers.fakes import fake_grid

GRID = fake_grid(10, 10)


def feature(kind, geometry, i=0):
    return PoiFeature(id=f"t:0:{i}", kind=kind, geometry=geometry, source="t/0")


def centre(row, col):
    return float(GRID.lon_centers()[col]), float(GRID.lat_centers()[row])


def test_dune_polygon_covers_the_cells_whose_centre_is_inside():
    mid = (GRID.west + GRID.east) / 2  # the boundary between columns 4 and 5
    ring = [[GRID.west - 0.01, GRID.south - 0.01], [mid, GRID.south - 0.01], [mid, GRID.north + 0.01],
            [GRID.west - 0.01, GRID.north + 0.01], [GRID.west - 0.01, GRID.south - 0.01]]
    masks = hazard_masks(GRID, PoiData((feature(PoiKind.DUNE_FIELD, {"type": "Polygon", "coordinates": [ring]}),)), 0)
    assert masks.dune[:, :5].all() and not masks.dune[:, 5:].any() and not masks.rsl.any()


def test_rsl_buffer_covers_cells_within_the_radius():
    _, dy = GRID.metric_spacing()
    lon, lat = centre(5, 5)
    poi = PoiData((feature(PoiKind.RSL, {"type": "Point", "coordinates": [lon, lat]}),))
    assert hazard_masks(GRID, poi, 0).rsl.sum() == 1 and hazard_masks(GRID, poi, 0).rsl[5, 5]
    wide = hazard_masks(GRID, poi, 1.5 * dy).rsl  # the 3 x 3 block (diagonal ~1.4 cells), not the next ring
    assert wide.sum() == 9 and wide[4:7, 4:7].all()


def test_other_kinds_and_point_dunes_make_no_hazard():
    lon, lat = centre(2, 2)
    poi = PoiData((feature(PoiKind.MINERAL_SULFATE, {"type": "Point", "coordinates": [lon, lat]}, 0),
                   feature(PoiKind.DUNE_FIELD, {"type": "Point", "coordinates": [lon, lat]}, 1)))
    masks = hazard_masks(GRID, poi, 10_000)
    assert not masks.dune.any() and not masks.rsl.any()


def test_empty_masks_and_negative_buffer():
    empty = HazardMasks.empty(GRID)
    assert empty.dune.shape == GRID.shape and empty.dune.dtype == bool and not empty.rsl.any()
    with pytest.raises(ValueError, match="rsl_buffer_m"):
        hazard_masks(GRID, PoiData(()), -1)


def test_masks_are_row_major_on_a_non_square_grid():
    grid = fake_grid(6, 9)
    lon, lat = float(grid.lon_centers()[7]), float(grid.lat_centers()[2])
    poi = PoiData((feature(PoiKind.RSL, {"type": "Point", "coordinates": [lon, lat]}),))
    rsl = hazard_masks(grid, poi, 0).rsl
    assert rsl.shape == (6, 9) and rsl.sum() == 1 and rsl[2, 7]
