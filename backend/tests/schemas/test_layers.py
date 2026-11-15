import pytest
from pydantic import ValidationError

from app.schemas.layers import LayerOneResponse, PointResponse


def test_point_response_allows_nodata():
    p = PointResponse(lon=-70, lat=-12, elevation_m=None, slope_deg=None, slope_class=None,
                      walkable=False, vehicle=False, approximate=True)
    assert p.elevation_m is None and p.approximate


def test_layer_one_response_requires_sources():
    with pytest.raises(ValidationError):
        LayerOneResponse(layer="base_imagery", default_source="ctx_coprates")
