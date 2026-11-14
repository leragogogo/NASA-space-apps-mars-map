"""/api/get-layer-one … four: thin wrappers around the layer getters."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from app.layers.poi.normalize import CATEGORIES
from app.layers.registry import Registry
from app.schemas.layers import LayerOneResponse, LayerTwoResponse, PointResponse

router = APIRouter(prefix="/api", tags=["layers"])
GEOJSON = {200: {"description": "GeoJSON FeatureCollection", "content": {"application/json": {}}}}


def _registry(request: Request) -> Registry:
    return request.app.state.layers


@router.get("/get-layer-one", response_model=LayerOneResponse, summary="Layer 1: base imagery sources")
def get_layer_one(request: Request):
    return _registry(request).get("base_imagery").describe()


@router.get("/get-layer-two", response_model=LayerTwoResponse, summary="Layer 2: relief and walkability")
def get_layer_two(request: Request):
    return _registry(request).get("relief").describe()


@router.get("/get-layer-two/walkability.png", response_class=Response, summary="Layer 2: walkability overlay",
            responses={200: {"content": {"image/png": {}}}})
def get_walkability_png(request: Request):
    return Response(_registry(request).get("relief").walkability_png(), media_type="image/png")


@router.get("/get-layer-two/point", response_model=PointResponse, summary="Layer 2: elevation and slope at a point")
def get_relief_point(request: Request, lon: float = Query(..., ge=-180, le=180),
                     lat: float = Query(..., ge=-90, le=90)):
    result = _registry(request).get("relief").point(lon, lat)
    if result is None:
        raise HTTPException(404, "Point is outside the area covered by the elevation data (East Melas demo area).")
    return result


@router.get("/get-layer-three", summary="Layer 3: points of interest", responses=GEOJSON)
def get_layer_three(request: Request, category: str | None = Query(
        None, description=f"Comma-separated filter. One or more of: {', '.join(CATEGORIES)}")):
    cats = None
    if category:
        cats = {c.strip() for c in category.split(",") if c.strip()}
        unknown = cats - set(CATEGORIES)
        if unknown:
            raise HTTPException(422, f"Unknown category: {', '.join(sorted(unknown))}. "
                                     f"Use one or more of: {', '.join(CATEGORIES)}")
    getter = _registry(request).get("poi")
    return JSONResponse(getter.describe(cats))


@router.get("/get-layer-four", summary="Layer 4: seasonal dust-storm risk", responses=GEOJSON)
def get_layer_four(request: Request, season: Literal["autumn", "winter", "spring", "summer"] = Query(...)):
    return JSONResponse(_registry(request).get("weather").describe(season))
