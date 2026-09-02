from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

from pyproj import Transformer
from shapely.geometry import Point, shape

_TRANSFORM_4326_TO_2263 = Transformer.from_crs(4326, 2263, always_xy=True)

DEFAULT_JOIN_RADIUS_FT = 150.0


def join_events_to_candidates(
    candidates: Sequence[Mapping[str, object]],
    events: Sequence[Mapping[str, object]],
    *,
    radius_ft: float = DEFAULT_JOIN_RADIUS_FT,
    lat_field: str = "latitude",
    lon_field: str = "longitude",
) -> Dict[str, List[dict]]:
    """Nearest-candidate spatial join in NY State Plane feet (EPSG:2263)."""
    matched: Dict[str, List[dict]] = {str(candidate["id"]): [] for candidate in candidates}
    if not candidates or not events:
        return matched

    candidate_xy = {
        str(candidate["id"]): _to_2263(float(candidate["lon"]), float(candidate["lat"]))
        for candidate in candidates
    }

    for event in events:
        event_lat = _as_float(event.get(lat_field))
        event_lon = _as_float(event.get(lon_field))
        if event_lat is None or event_lon is None:
            continue
        event_x, event_y = _to_2263(event_lon, event_lat)
        nearest_id = None
        nearest_distance = None
        for candidate_id, (candidate_x, candidate_y) in candidate_xy.items():
            distance = math.hypot(candidate_x - event_x, candidate_y - event_y)
            if nearest_distance is None or distance < nearest_distance:
                nearest_id = candidate_id
                nearest_distance = distance
        if nearest_id is None or nearest_distance is None or nearest_distance > radius_ft:
            continue
        matched[nearest_id].append(dict(event))
    return matched


def assign_neighborhoods(
    candidates: Sequence[Mapping[str, object]],
    nta_geojson: Mapping[str, object] | Path,
) -> Dict[str, Dict[str, str]]:
    collection = _load_geojson(nta_geojson)
    features = collection.get("features") or []
    polygons = []
    for feature in features:
        geometry = feature.get("geometry")
        properties = feature.get("properties") or {}
        if not geometry:
            continue
        polygons.append(
            (
                shape(geometry),
                str(_nta_id(properties)),
                str(_nta_name(properties)),
            )
        )

    assigned: Dict[str, Dict[str, str]] = {}
    for candidate in candidates:
        point = Point(float(candidate["lon"]), float(candidate["lat"]))
        neighborhood_id = "UNKNOWN"
        neighborhood_name = "Unknown"
        for polygon, nta_id, nta_name in polygons:
            if polygon.contains(point) or polygon.intersects(point):
                neighborhood_id = nta_id
                neighborhood_name = nta_name
                break
        assigned[str(candidate["id"])] = {
            "neighborhood_id": neighborhood_id,
            "neighborhood_name": neighborhood_name,
        }
    return assigned


def points_within_radius(
    candidates: Sequence[Mapping[str, object]],
    points: Sequence[Mapping[str, object]],
    *,
    radius_ft: float,
    lat_field: str = "latitude",
    lon_field: str = "longitude",
) -> Dict[str, bool]:
    flagged = {str(candidate["id"]): False for candidate in candidates}
    point_xy: list[tuple[float, float]] = []
    for point in points:
        lat = _as_float(point.get(lat_field))
        lon = _as_float(point.get(lon_field))
        if lat is None or lon is None:
            continue
        point_xy.append(_to_2263(lon, lat))
    if not point_xy:
        return flagged
    for candidate in candidates:
        candidate_x, candidate_y = _to_2263(float(candidate["lon"]), float(candidate["lat"]))
        flagged[str(candidate["id"])] = any(
            math.hypot(candidate_x - px, candidate_y - py) <= radius_ft for px, py in point_xy
        )
    return flagged


def crash_counts_from_join(matched: Mapping[str, Sequence[Mapping[str, object]]]) -> Dict[str, int]:
    return {candidate_id: len(events) for candidate_id, events in matched.items()}


def load_json_records(path: Path) -> list:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and "features" in payload:
        return payload["features"]
    raise ValueError(f"unsupported JSON records at {path}")


def _load_geojson(source: Mapping[str, object] | Path) -> dict:
    if isinstance(source, Path):
        return json.loads(source.read_text(encoding="utf-8"))
    return dict(source)


def _nta_id(properties: Mapping[str, object]) -> str:
    for key in ("NTA2020", "nta2020", "ntacode", "NTACode"):
        if properties.get(key):
            return str(properties[key])
    return "UNKNOWN"


def _nta_name(properties: Mapping[str, object]) -> str:
    for key in ("NTAName", "ntaname", "NTAName2020"):
        if properties.get(key):
            return str(properties[key])
    return "Unknown"


def _to_2263(lon: float, lat: float) -> tuple[float, float]:
    x, y = _TRANSFORM_4326_TO_2263.transform(lon, lat)
    return float(x), float(y)


def _as_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
