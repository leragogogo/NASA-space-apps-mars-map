"""Step 4: the node table: every layer's per-node data, flattened to 1-D arrays in node-id order.

Required by GraphData: lon, lat, elev_m, valid. Also stored: slope_deg, nearest_poi_dist_m,
nearest_poi_id, optional roughness_m, and the per-season weather as weather_risk_<k> /
weather_conf_<k> (k = index in SEASONS). Weather is stored for warnings only; it never enters the
edge costs.
"""
from __future__ import annotations

import numpy as np

from app.layers.contracts import SEASONS, GraphInputs


def weather_risk_key(season_index: int) -> str:
    return f"weather_risk_{season_index}"


def weather_conf_key(season_index: int) -> str:
    return f"weather_conf_{season_index}"


def build_node_table(inputs: GraphInputs) -> dict[str, np.ndarray]:
    grid, relief, weather, poi = inputs.grid, inputs.relief, inputs.weather, inputs.poi
    n = grid.n_nodes
    lon, lat = grid.node_lonlat()
    node: dict[str, np.ndarray] = {
        "lon": lon, "lat": lat,
        "elev_m": relief.elev_m.reshape(-1).copy(),
        "valid": relief.valid.reshape(-1).copy(),
        "slope_deg": relief.slope_deg.reshape(-1).copy(),
    }
    if relief.roughness_m is not None:
        node["roughness_m"] = relief.roughness_m.reshape(-1).copy()
    node["nearest_poi_dist_m"] = (np.full(n, np.nan, dtype=np.float32) if poi.nearest_poi_dist_m is None
                                  else poi.nearest_poi_dist_m.reshape(-1).copy())
    node["nearest_poi_id"] = (np.full(n, -1, dtype=np.int32) if poi.nearest_poi_id is None
                              else poi.nearest_poi_id.reshape(-1).copy())
    for k in range(len(SEASONS)):
        node[weather_risk_key(k)] = weather.risk[k].reshape(-1).copy()
        node[weather_conf_key(k)] = weather.confidence[k].reshape(-1).copy()
    return node
