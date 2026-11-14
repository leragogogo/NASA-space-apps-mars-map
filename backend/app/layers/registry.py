"""Builds the four layer getters once at startup and hands them to the API (and later the master graph)."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.layers.base import LayerUnavailable
from app.layers.base_imagery.getter import BaseImageryGetter
from app.layers.poi.getter import PoiGetter
from app.layers.relief.getter import ReliefGetter
from app.layers.weather.getter import WeatherGetter
from app.tiles.store import TileStore

log = logging.getLogger(__name__)


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


def build_registry(settings) -> Registry:
    store = TileStore(settings.raw_dir / "tiles", settings.tile_sources, settings.aoi)
    return Registry(store, {
        "base_imagery": _try("base_imagery", lambda: BaseImageryGetter(store)),
        "relief": _try("relief", lambda: ReliefGetter(settings, store)),
        "poi": _try("poi", lambda: PoiGetter(settings, store)),
        "weather": _try("weather", lambda: WeatherGetter(settings)),
    })
