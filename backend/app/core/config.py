"""Backend settings. Everything that may change after review (paths, thresholds, colours) lives here."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# Demo area (west, south, east, north), longitude -180..180. Same box as scripts/download_data.py.
AOI = (-71.8, -13.4, -68.0, -10.0)


@dataclass(frozen=True)
class SlopeClass:
    id: str
    label: str
    min_deg: float
    max_deg: float
    color: str  # hex; used by the walkability PNG and the legend
    walkable: bool
    vehicle: bool


STATUS_PLACEHOLDER = "placeholder"
STATUS_CONFIRMED = "confirmed"

# Built-in defaults, used only when no configuration file is loaded (config/mars.yaml is the source of truth).
# Thresholds are unconfirmed by the product owner (SKILL.md section 5): keep them configurable.
SLOPE_CLASSES = (
    SlopeClass("easy_walk", "Easy walk", 0, 5, "#1a9850", True, True),
    SlopeClass("walkable", "Walkable", 5, 15, "#91cf60", True, True),
    SlopeClass("vehicle_only", "Vehicle only", 15, 25, "#fee08b", False, True),
    SlopeClass("vehicle_limit", "Hard / vehicle limit", 25, 35, "#fc8d59", False, True),
    SlopeClass("impassable", "Impassable", 35, 90, "#d73027", False, False),
)


@dataclass(frozen=True)
class TileSourceDef:
    folder: str        # folder under data/raw/tiles (the Trek layer label)
    title: str
    layer: str         # base_imagery | relief | poi
    coverage_note: str


# Short public id -> tile folder. Only these sources are ever served.
TILE_SOURCES = {
    "ctx_coprates": TileSourceDef("Coprates_EMelas_Chasm_CTX_BlockAdj_dd", "CTX mosaic, Coprates / East Melas",
                                  "base_imagery", "98 % of the demo area"),
    "ctx_global": TileSourceDef("CTX_beta01_uncontrolled_5m_Caltech", "CTX global mosaic (fallback)", "base_imagery",
                                "~92 % of the demo area; gaps in the south-east where Trek stores truncated tiles"),
    "hirise": TileSourceDef("HiRISE_Global", "HiRISE (zoom-in detail)", "base_imagery",
                            "~17 % of the demo area, scattered footprints"),
    "hillshade_color": TileSourceDef("Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw",
                                     "MOLA + HRSC colour shaded relief", "relief", "~98 % of the demo area"),
    "hillshade_ctx": TileSourceDef("CTX_Shade_East_Melas", "CTX shaded relief, East Melas", "relief",
                                   "~48 % of the demo area, in strips"),
    "crism_sulfate": TileSourceDef("MC18_PolySulfate_Mineral_IndicatorV2_SP", "CRISM polyhydrated sulfate indicator",
                                   "poi", "~70 % of the demo area"),
}

RISK_COLORS = {"Low": "#2e7d32", "Moderate": "#f9a825", "High": "#c62828"}


def _default_data_dir() -> Path:
    return Path(os.environ.get("MARS_DATA_DIR", REPO_ROOT / "data"))


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=_default_data_dir)
    aoi: tuple = AOI
    slope_classes: tuple = SLOPE_CLASSES
    tile_sources: dict = field(default_factory=lambda: dict(TILE_SOURCES))
    risk_colors: dict = field(default_factory=lambda: dict(RISK_COLORS))
    poi_sample_radius_km: float = 2.0
    # Auth. No default secret: create_app refuses to start without JWT_SECRET_KEY.
    jwt_secret_key: str | None = field(default_factory=lambda: os.environ.get("JWT_SECRET_KEY"))
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    @property
    def database_url(self) -> str:
        """MARS_DATABASE_URL, else a SQLite file in the (gitignored) data folder."""
        return os.environ.get("MARS_DATABASE_URL", f"sqlite:///{self.data_dir / 'app.db'}")
    # Shared grid: the 200 m DEM divided by this factor. Display and routing share it. 1 = the native 200 m grid
    # (1.29 M nodes, 10.3 M edges; routes in seconds with the NumPy/SciPy engine); 2 -> ~400 m, ~320k nodes.
    grid_coarsen: int = 1
    # Routing (SKILL.md section 10). Capacities are placeholders until confirmed by the product owner:
    # {profile: {resource: capacity}}; empty = no budget warnings.
    capacities: dict = field(default_factory=dict)
    reserve_margin: float = 0.2
    max_snap_distance_m: float = 1000.0
    # Per-profile model parameters from the configuration file ({profile: {parameter: value}}); parameters that are
    # not listed keep the defaults of app/routing/profiles/params.py.
    profiles: dict = field(default_factory=dict)
    # Configuration sections the product owner has not signed off yet (see config/mars.yaml, `confirmation`).
    unconfirmed: tuple = ()

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def graph_file(self) -> Path:
        return self.data_dir / "graph" / "graph.npz"

    @property
    def derived_dir(self) -> Path:
        return self.data_dir / "derived"
