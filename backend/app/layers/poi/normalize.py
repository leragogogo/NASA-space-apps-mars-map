"""Maps each downloaded Trek vector dataset to one common feature format.

Every output feature has properties: id, category, name, description, source, raw (original fields).
"""
from __future__ import annotations

CATEGORIES = ("mineral", "water_activity", "exploration_zone", "dunes", "geology", "place_name", "observation")
EZ_NOTE = "Candidate human exploration zone (NASA Exploration Zones workshop, 2015)."


def _s(value) -> str:
    return "" if value is None else str(value).strip()


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _links(p) -> str:
    links = [x for x in (_s(p.get("abstract_l")), _s(p.get("presentati"))) if x]
    return EZ_NOTE + (" Details: " + ", ".join(links) if links else "")


def _aqueous(p):
    cls = _s(p.get("Class")) or "aqueous mineral"
    return "mineral", f"{_cap(cls)} detection", f"Orbital detection of {cls} (aqueous mineral distribution map)."


def _hydrous(p):
    inst = _s(p.get("Instrument")) or "OMEGA/CRISM"
    return "mineral", "Hydrous mineral detection", f"Hydrous mineral detection by {inst}."


def _rsl(p):
    kind = _s(p.get("Type")) or "recurring slope lineae"
    ref = _s(p.get("Ref"))
    desc = "Seasonal dark streaks on slopes, possibly linked to briny water." + (f" Reference: {ref}." if ref else "")
    return "water_activity", _cap(kind), desc


def _ez_centre(p):
    return "exploration_zone", f"{_s(p.get('name'))} exploration zone (centre)", _links(p)


def _ez_roi(p):
    return ("exploration_zone", f"{_s(p.get('ez_name'))} ROI {_s(p.get('name'))}",
            "Region of interest inside a candidate human exploration zone (NASA workshop, 2015).")


def _ez_boundary(p):
    return "exploration_zone", f"{_s(p.get('name'))} exploration zone boundary", _links(p)


def _dunes(p):
    kind = _s(p.get("Dune_Type")) or "unknown"
    return "dunes", f"Dune field {_s(p.get('Dune_ID'))}", f"Dune field (type codes: {kind}); a sign of active wind."


def _geology(p):
    return "geology", f"{_s(p.get('UnitDesc'))} ({_s(p.get('Unit'))})", "Geologic map unit (USGS SIM 3292)."


def _place(p):
    parts = [x for x in (_s(p.get("type")), _s(p.get("origin"))) if x]
    return "place_name", _s(p.get("name")), ". ".join(x.rstrip(".") for x in parts) + "." if parts else "IAU name."


def _crism(p):
    date = _s(p.get("UTCstart"))[:10]
    return ("observation", f"CRISM observation {_s(p.get('ProductId'))}",
            "CRISM targeted observation footprint" + (f", acquired {date}." if date else "."))


# file stem -> (source title, mapper(properties) -> (category, name, description))
DATASETS = {
    "Aquieous_Mineral_Distribution_Options_clon0__0": ("Aqueous Mineral Distribution (NASA Trek)", _aqueous),
    "Hydrous_Mineral_Detections_OMEGA_CRISM_clon0__0": ("Hydrous Mineral Detections, OMEGA/CRISM (NASA Trek)", _hydrous),
    "RSLs_Gullies_New_IcyCraters_clon0__0": ("RSLs, Fresh Gullies, New and Icy Craters (NASA Trek)", _rsl),
    "EZMars__0": ("NASA Human Exploration Zones: zones (NASA Trek)", _ez_centre),
    "EZMars__3": ("NASA Human Exploration Zones: regions of interest (NASA Trek)", _ez_roi),
    "EZMars__4": ("NASA Human Exploration Zones: zone boundaries (NASA Trek)", _ez_boundary),
    "Dune_Field__0": ("Mars Global Digital Dune Database (NASA Trek)", _dunes),
    "SIM3292_Global_Geology__0": ("Geologic Map of Mars, USGS SIM 3292 (NASA Trek)", _geology),
    "combinedNom__0": ("IAU Mars nomenclature (NASA Trek)", _place),
    "mars_mro_crism_mtrdr_c0a_humex_frt_sites__0": ("CRISM targeted observations (NASA Trek)", _crism),
}
CLIP_TO_AOI = {"SIM3292_Global_Geology__0"}


def normalize_lon(coords):
    """Recursively convert 0..360 east longitudes to -180..180."""
    if coords and isinstance(coords[0], (int, float)):
        x = coords[0] - 360 if coords[0] > 180 else coords[0]
        return [x, *coords[1:]]
    return [normalize_lon(c) for c in coords]


def normalize_feature(stem: str, index: int, feature: dict) -> dict:
    title, mapper = DATASETS[stem]
    props = feature.get("properties") or {}
    category, name, description = mapper(props)
    geom = feature.get("geometry")
    if geom:
        geom = {**geom, "coordinates": normalize_lon(geom["coordinates"])}
    return {"type": "Feature", "geometry": geom,
            "properties": {"id": f"{stem}:{props.get('FID', index)}", "category": category, "name": name,
                           "description": description, "source": title, "raw": props}}
