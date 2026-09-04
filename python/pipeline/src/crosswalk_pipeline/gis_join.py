from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

import numpy as np
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.strtree import STRtree
from sklearn.neighbors import BallTree

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

    candidate_ids = [str(candidate["id"]) for candidate in candidates]
    candidate_xy = np.array(
        [_to_2263(float(candidate["lon"]), float(candidate["lat"])) for candidate in candidates],
        dtype=float,
    )
    tree = BallTree(candidate_xy, metric="euclidean")

    event_xy: list[tuple[float, float]] = []
    event_keep: list[dict] = []
    for event in events:
        event_lat = _as_float(event.get(lat_field))
        event_lon = _as_float(event.get(lon_field))
        if event_lat is None or event_lon is None:
            continue
        event_xy.append(_to_2263(event_lon, event_lat))
        event_keep.append(dict(event))
    if not event_xy:
        return matched

    distances, indices = tree.query(np.asarray(event_xy, dtype=float), k=1)
    for event, distance, index in zip(event_keep, distances[:, 0], indices[:, 0]):
        if float(distance) <= radius_ft:
            matched[candidate_ids[int(index)]].append(event)
    return matched


def assign_neighborhoods(
    candidates: Sequence[Mapping[str, object]],
    nta_geojson: Mapping[str, object] | Path,
) -> Dict[str, Dict[str, str]]:
    collection = _load_geojson(nta_geojson)
    features = collection.get("features") or []
    polygons = []
    meta: list[tuple[str, str, str]] = []
    for feature in features:
        geometry = feature.get("geometry")
        properties = feature.get("properties") or {}
        if not geometry:
            continue
        geom = shape(geometry)
        polygons.append(geom)
        meta.append((_nta_id(properties), _nta_name(properties), _nta_borough(properties)))

    tree = STRtree(polygons) if polygons else None
    assigned: Dict[str, Dict[str, str]] = {}
    for candidate in candidates:
        point = Point(float(candidate["lon"]), float(candidate["lat"]))
        neighborhood_id = "UNKNOWN"
        neighborhood_name = "Unknown"
        borough = "Unknown"
        hit_idx = None
        if tree is not None and polygons:
            hits = tree.query(point)
            for idx in np.atleast_1d(hits):
                polygon = polygons[int(idx)]
                if polygon.contains(point) or polygon.intersects(point) or polygon.distance(point) <= 1e-8:
                    hit_idx = int(idx)
                    break
            if hit_idx is None:
                # Boundary / water-adjacent nodes often miss contains by a hair.
                distances = [geom.distance(point) for geom in polygons]
                nearest = int(np.argmin(distances))
                if distances[nearest] < 0.01:
                    hit_idx = nearest
        if hit_idx is not None:
            neighborhood_id, neighborhood_name, borough = meta[hit_idx]
        assigned[str(candidate["id"])] = {
            "neighborhood_id": neighborhood_id,
            "neighborhood_name": neighborhood_name,
            "borough": borough,
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
    tree = BallTree(np.asarray(point_xy, dtype=float), metric="euclidean")
    candidate_xy = np.array(
        [_to_2263(float(candidate["lon"]), float(candidate["lat"])) for candidate in candidates],
        dtype=float,
    )
    hits = tree.query_radius(candidate_xy, r=radius_ft)
    for candidate, neighbors in zip(candidates, hits):
        flagged[str(candidate["id"])] = len(neighbors) > 0
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


def _nta_borough(properties: Mapping[str, object]) -> str:
    for key in ("BoroName", "boroname", "borough"):
        if properties.get(key):
            return str(properties[key])
    nta_id = _nta_id(properties)
    prefix = nta_id[:2].upper()
    return {
        "MN": "Manhattan",
        "BX": "Bronx",
        "BK": "Brooklyn",
        "QN": "Queens",
        "SI": "Staten Island",
    }.get(prefix, "Unknown")


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
