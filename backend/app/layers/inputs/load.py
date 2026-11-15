"""load_all: every ingestion on one grid -> GraphInputs, the only thing the graph builder reads
(layer-ingestion.md section 5). Raises LayerDataError when a layer's data is missing or invalid."""
from __future__ import annotations

from app.layers.contracts import GraphInputs, GridSpec
from app.layers.poi.ingest import ingest_poi
from app.layers.relief.ingest import grid_for, ingest_relief
from app.layers.validate import validate_inputs
from app.layers.weather.ingest import ingest_weather


def load_all(settings, grid: GridSpec | None = None) -> GraphInputs:
    grid = grid or grid_for(settings)
    inputs = GraphInputs(grid=grid, relief=ingest_relief(settings, grid), weather=ingest_weather(settings, grid),
                         poi=ingest_poi(settings, grid))
    validate_inputs(inputs)
    return inputs
