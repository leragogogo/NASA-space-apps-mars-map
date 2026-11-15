"""What every layer getter has in common."""
from __future__ import annotations

from typing import Protocol


class LayerUnavailable(Exception):
    """A layer's data is missing or unreadable. The API answers 503 with `detail` and `fix`."""

    def __init__(self, detail: str, fix: str):
        super().__init__(detail)
        self.detail = detail
        self.fix = fix


class LayerGetter(Protocol):
    name: str

    def describe(self, *args, **kwargs) -> dict:
        """Summary returned by the layer's /api/get-layer-* endpoint."""

    def sample(self, lon: float, lat: float, season: str | None = None):
        """What this layer knows about one point (input for the master graph)."""
