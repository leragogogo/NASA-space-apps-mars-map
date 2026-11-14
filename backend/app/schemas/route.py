"""API models for POST /api/route. The backend owns this format; the frontend consumes it."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.resources import ProfileId
from app.layers.contracts import SEASONS
from app.routing.contracts import DropReason, EndMode, RouteLimits

_LIMITS = RouteLimits()


class LonLat(BaseModel):
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)


class RouteRequest(BaseModel):
    profile: ProfileId
    start: LonLat
    destinations: list[LonLat] = Field(min_length=1, max_length=_LIMITS.max_destinations)
    end_mode: EndMode = EndMode.ROUND_TRIP
    end: LonLat | None = None
    time_limit_s: float = _LIMITS.default_time_limit_s
    season: str | None = None

    @field_validator("time_limit_s")
    @classmethod
    def _clamp_time(cls, v: float) -> float:
        return _LIMITS.clamp_time_limit(v)

    @field_validator("season")
    @classmethod
    def _known_season(cls, v: str | None) -> str | None:
        if v is not None and v not in SEASONS:
            raise ValueError(f"season must be one of {SEASONS}")
        return v

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
