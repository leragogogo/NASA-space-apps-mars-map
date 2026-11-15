"""Builds the four layers once at startup (ingest -> service) and hands them to the API."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.layers.base import LayerUnavailable
from app.layers.base_imagery.ingest import ingest_imagery
from app.layers.base_imagery.service import BaseImageryGetter
from app.layers.contracts import LayerDataError
from app.layers.poi.ingest import ingest_poi
from app.layers.poi.service import PoiGetter
from app.layers.relief.ingest import grid_for, ingest_relief
from app.layers.relief.service import ReliefGetter
from app.layers.weather.ingest import ingest_weather
from app.layers.weather.service import WeatherGetter
from app.tiles.store import TileStore

log = logging.getLogger(__name__)

FIX = {  # what to run when a layer's data is missing (shown in the HTTP 503 `fix` field)
    "base_imagery": "python scripts/download_data.py --only tiles",
    "relief": "python scripts/download_data.py --only dem",
    "poi": "python scripts/download_data.py --only pois",
    "weather": "python scripts/download_data.py --only weather",
}


@dataclass
class Registry:
    tiles: TileStore
    layers: dict  # name -> getter, or the LayerUnavailable raised while building it

    def get(self, name: str):
        """The getter for `name`; raises LayerUnavailable (-> HTTP 503) if its data is missing."""
        layer = self.layers[name]
        if isinstance(layer, LayerUnavailable):
            raise layer
        return layer

    def status(self) -> dict:
        return {n: "ok" if not isinstance(g, LayerUnavailable) else g.detail for n, g in self.layers.items()}


def _try(name, factory):
    try:
        return factory()
    except LayerUnavailable as ex:
        log.warning("Layer %s unavailable: %s (fix: %s)", name, ex.detail, ex.fix)
        return ex
    except LayerDataError as ex:  # ingest failed: same 503 as a missing layer
        log.warning("Layer %s unavailable: %s (fix: %s)", name, ex.message, FIX[name])
        return LayerUnavailable(ex.message, FIX[name])


def build_registry(settings) -> Registry:
    store = TileStore(settings.raw_dir / "tiles", settings.tile_sources, settings.aoi)
    grid = grid_for(settings)
    return Registry(store, {
        "base_imagery": _try("base_imagery", lambda: BaseImageryGetter(settings, ingest_imagery(settings, store))),
        "relief": _try("relief", lambda: ReliefGetter(settings, store, ingest_relief(settings, grid))),
        "poi": _try("poi", lambda: PoiGetter(settings, store, ingest_poi(settings, grid))),
        "weather": _try("weather", lambda: WeatherGetter(settings, ingest_weather(settings, grid))),
    })
