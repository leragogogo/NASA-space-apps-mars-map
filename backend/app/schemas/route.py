"""API models for POST /api/route. The backend owns this format; the frontend consumes it."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.resources import ProfileId
from app.routing.contracts import DropReason, EndMode


class LonLat(BaseModel):
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)


class RouteRequest(BaseModel):
    profile: ProfileId
    start: LonLat
    destinations: list[LonLat] = Field(min_length=1)  # the maximum comes from the configuration, checked per request
    end_mode: EndMode = EndMode.ROUND_TRIP
    end: LonLat | None = None
    time_limit_s: float | None = None  # solver time budget in s; None = the configured default, clamped to the configured range
    season: Literal["autumn", "winter", "spring", "summer"] | None = None  # same keys as /api/get-layer-four

    @model_validator(mode="after")
    def _end_matches_mode(self):
        if (self.end_mode == EndMode.FIXED) != (self.end is not None):
            raise ValueError("end is required if and only if end_mode is 'fixed'")
        return self


class SnappedPoint(LonLat):
    distance_m: float


class SnappedPoints(BaseModel):
    start: SnappedPoint
    destinations: list[SnappedPoint]
    end: SnappedPoint | None = None


class LegOut(BaseModel):
    from_: str | int = Field(alias="from")  # "start" or a destination index
    to: str | int
    weight: float
    resources: dict[str, float] = {}

    model_config = {"populate_by_name": True}


class DroppedStopOut(BaseModel):
    index: int
    point: LonLat
    reason: DropReason


class RouteResponse(BaseModel):
    profile: ProfileId
    path: dict[str, Any]  # GeoJSON LineString, coordinates [lon, lat] (Leaflet needs [lat, lon])
    stop_order: list[int]
    legs: list[LegOut]
    total_weight: float
    resources: dict[str, float]
    dropped: list[DroppedStopOut] = []
    snapped: SnappedPoints
    warnings: list[str] = []
    # Body mass (kg) of the requesting user that the o2/co2/water estimates were computed for; null when the
    # profile does not depend on it (car) or the reference mass was used.
    body_mass_kg: float | None = None
