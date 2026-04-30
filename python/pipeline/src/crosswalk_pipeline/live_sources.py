from __future__ import annotations

import math
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import geopandas as gpd
import pandas as pd
import requests
from pyproj import Transformer
from pyogrio import read_dataframe
from shapely.geometry import Point

from .config import PATHS
from .io_utils import write_json
from .models import CandidateRecord

LION_DOWNLOAD_URL = (
    "https://data.cityofnewyork.us/api/views/2v4z-66xt/files/"
    "a3e46353-0b43-4b3b-a4fd-9bb042ccabb7?download=1"
)
SCHOOL_ZONES_CSV_URL = "https://data.cityofnewyork.us/api/views/cmjf-yawu/rows.csv?accessType=DOWNLOAD"
PAVEMENT_311_URL = (
    "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
    "?%24select=unique_key,created_date,complaint_type,descriptor,latitude,longitude,incident_address"
    "&%24where=complaint_type=%27Street%20Condition%27"
    "%20AND%20descriptor%20in(%27Line/Marking%20-%20Faded%27,%27Line/Marking%20-%20After%20Repaving%27)"
    "%20AND%20created_date%20%3E=%20%272020-01-01T00:00:00%27"
    "%20AND%20latitude%20is%20not%20null%20AND%20longitude%20is%20not%20null"
    "%20AND%20latitude%20between%2040.7000%20and%2040.7205"
    "%20AND%20longitude%20between%20-74.02%20and%20-73.99"
    "&%24limit=50000"
)

LOWER_MANHATTAN_BOUNDS = {
    "min_lon": -74.02,
    "max_lon": -73.99,
    "min_lat": 40.7000,
    "max_lat": 40.7205,
}

LOWER_MANHATTAN_LABEL = "Lower Manhattan south of Canal Street"
MAX_INTERSECTIONS = 8

_TRANSFORM_4326_TO_2263 = Transformer.from_crs(4326, 2263, always_xy=True)


@dataclass(frozen=True)
class LiveSourceVersions:
    lion: str = "NYC LION 26a"
    imagery: str = "NYS 2024 orthos via ArcGIS MapServer"
    school_zones: str = "School Zones 2024-2025 (Elementary School)"
    service_requests_311: str = "NYC Open Data 311 pavement-marking complaints since 2020"


def ensure_live_sources() -> LiveSourceVersions:
    PATHS.raw_dir.mkdir(parents=True, exist_ok=True)

    if not PATHS.lion_zip_path.exists():
        _download_file(LION_DOWNLOAD_URL, PATHS.lion_zip_path)

    if not PATHS.lion_gdb_path.exists():
        PATHS.lion_unzipped_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(PATHS.lion_zip_path, "r") as archive:
            archive.extractall(PATHS.lion_unzipped_dir)

    if not PATHS.school_zones_csv_path.exists():
        _download_file(SCHOOL_ZONES_CSV_URL, PATHS.school_zones_csv_path)

    pavement_311_path = PATHS.raw_dir / "pavement_marking_311.json"
    _download_json(PAVEMENT_311_URL, pavement_311_path)

    return LiveSourceVersions()


def build_live_candidates() -> List[CandidateRecord]:
    lion = _load_lion_segments()
    nodes = _load_lower_manhattan_nodes()

    node_ids = set(nodes["NODEID"].astype(int).tolist())
    lion["NodeIDFrom"] = pd.to_numeric(lion["NodeIDFrom"], errors="coerce").fillna(0).astype(int)
    lion["NodeIDTo"] = pd.to_numeric(lion["NodeIDTo"], errors="coerce").fillna(0).astype(int)
    lion["LBoro"] = pd.to_numeric(lion["LBoro"], errors="coerce").fillna(0).astype(int)
    lion["RBoro"] = pd.to_numeric(lion["RBoro"], errors="coerce").fillna(0).astype(int)
    lion = lion[(lion["LBoro"] == 1) | (lion["RBoro"] == 1)].copy()
    lion = lion[(lion["NodeIDFrom"].isin(node_ids)) | (lion["NodeIDTo"].isin(node_ids))].copy()
    lion = lion[lion["Street"].map(_is_usable_street)]

    segments_by_node: Dict[int, List[dict]] = defaultdict(list)
    for row in lion.itertuples(index=False):
        segment = {
            "street": str(row.Street).strip(),
            "from_id": int(row.NodeIDFrom),
            "to_id": int(row.NodeIDTo),
            "width": float(row.StreetWidth_Max or 0.0),
            "geometry": row.geometry,
        }
        if segment["from_id"] in node_ids:
            segments_by_node[segment["from_id"]].append(segment)
        if segment["to_id"] in node_ids and segment["to_id"] != segment["from_id"]:
            segments_by_node[segment["to_id"]].append(segment)

    node_lookup = {int(row.NODEID): row for row in nodes.itertuples(index=False)}
    ranked_nodes: List[Tuple[float, int, List[Tuple[str, List[dict], float]]]] = []

    for node_id, segments in segments_by_node.items():
        grouped = _group_segments_by_street(node_id, segments, node_lookup[node_id].geometry)
        if len(grouped) < 2:
            continue
        primary = grouped[:2]
        score = sum(group[2] for group in primary) + len(grouped) * 10.0
        ranked_nodes.append((score, node_id, primary))

    ranked_nodes.sort(key=lambda item: item[0], reverse=True)

    candidates: List[CandidateRecord] = []
    for _, node_id, primary_groups in ranked_nodes[:MAX_INTERSECTIONS]:
        node = node_lookup[node_id]
        intersection_streets = [group[0] for group in primary_groups]
        intersection_label = " & ".join(_format_street_name(name) for name in intersection_streets)
        lat = float(node.lat)
        lon = float(node.lon)
        primary_heading = _mean_heading(
            [_segment_heading(node.geometry, segment["geometry"]) for segment in primary_groups[0][1]]
        )
        secondary_heading = _mean_heading(
            [_segment_heading(node.geometry, segment["geometry"]) for segment in primary_groups[1][1]]
        )
        candidates.append(
            CandidateRecord(
                id=f"lm-live-{node_id}",
                intersection_label=intersection_label,
                leg_label="",
                lat=lat,
                lon=lon,
                year=2024,
                paint_missing_ratio=0.0,
                stripe_break_ratio=0.0,
                contrast_score=0.0,
                occlusion_penalty=0.0,
                school_zone=False,
                pavement_marking_311_count_since_2020=0,
                heading_degrees=primary_heading,
                secondary_heading_degrees=secondary_heading,
            )
        )

    return candidates


def annotate_school_zones(candidates: List[CandidateRecord]) -> Dict[str, bool]:
    school_zones = pd.read_csv(PATHS.school_zones_csv_path)
    school_zones = school_zones[school_zones["BORO"] == "M"].copy()
    school_zones["geometry"] = gpd.GeoSeries.from_wkt(school_zones["the_geom"])
    school_zones_gdf = gpd.GeoDataFrame(school_zones, geometry="geometry", crs="EPSG:4326")

    result: Dict[str, bool] = {}
    for candidate in candidates:
        point = Point(candidate.lon, candidate.lat)
        result[candidate.id] = bool(school_zones_gdf.contains(point).any())
    return result


def annotate_311_counts(candidates: List[CandidateRecord]) -> Dict[str, int]:
    details = annotate_311_details(candidates)
    return {candidate_id: len(entries) for candidate_id, entries in details.items()}


def annotate_311_details(candidates: List[CandidateRecord]) -> Dict[str, List[Dict[str, str]]]:
    pavement_311_path = PATHS.raw_dir / "pavement_marking_311.json"
    complaints = pd.read_json(pavement_311_path)
    if complaints.empty:
        return {candidate.id: [] for candidate in candidates}

    complaints["latitude"] = pd.to_numeric(complaints["latitude"], errors="coerce")
    complaints["longitude"] = pd.to_numeric(complaints["longitude"], errors="coerce")
    complaints = complaints.dropna(subset=["latitude", "longitude"]).copy()

    candidate_points = {
        candidate.id: _TRANSFORM_4326_TO_2263.transform(candidate.lon, candidate.lat) for candidate in candidates
    }
    candidate_streets = {
        candidate.id: [part.strip().upper() for part in candidate.intersection_label.split("&")] for candidate in candidates
    }

    matched: Dict[str, List[Dict[str, str]]] = {candidate.id: [] for candidate in candidates}
    for complaint in complaints.itertuples(index=False):
        complaint_x, complaint_y = _TRANSFORM_4326_TO_2263.transform(
            float(complaint.longitude), float(complaint.latitude)
        )
        incident_address = str(getattr(complaint, "incident_address", "") or "").upper()
        nearest_id = None
        nearest_distance = None
        for candidate_id, (candidate_x, candidate_y) in candidate_points.items():
            distance = _distance(candidate_x, candidate_y, complaint_x, complaint_y)
            if nearest_distance is None or distance < nearest_distance:
                nearest_id = candidate_id
                nearest_distance = distance

        if nearest_id is None or nearest_distance is None:
            continue

        matched_here = False
        if nearest_distance <= 150.0:
            matched_here = True
        elif nearest_distance <= 500.0:
            streets = candidate_streets[nearest_id]
            matched_here = any(street and street in incident_address for street in streets)

        if matched_here:
            unique_key = str(getattr(complaint, "unique_key", "") or "").strip()
            matched[nearest_id].append(
                {
                    "unique_key": unique_key,
                    "created_date": str(getattr(complaint, "created_date", "") or ""),
                    "descriptor": str(getattr(complaint, "descriptor", "") or ""),
                    "incident_address": str(getattr(complaint, "incident_address", "") or ""),
                    "url": (
                        "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
                        f"?$select=unique_key,created_date,closed_date,agency,agency_name,"
                        f"complaint_type,descriptor,descriptor_2,location_type,incident_address,"
                        f"status,resolution_description"
                        f"&$where=unique_key=%27{unique_key}%27"
                    ),
                }
            )

    for candidate_id, entries in matched.items():
        entries.sort(key=lambda entry: entry["created_date"], reverse=True)

    return matched


def _download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    destination.write_bytes(response.content)


def _download_json(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    destination.write_text(response.text, encoding="utf-8")


def _load_lower_manhattan_nodes() -> gpd.GeoDataFrame:
    nodes = read_dataframe(PATHS.lion_gdb_path, layer="node", columns=["NODEID", "VIntersect"])
    nodes_wgs84 = nodes.to_crs(4326)
    bounds = LOWER_MANHATTAN_BOUNDS
    mask = (
        (nodes_wgs84.geometry.x >= bounds["min_lon"])
        & (nodes_wgs84.geometry.x <= bounds["max_lon"])
        & (nodes_wgs84.geometry.y >= bounds["min_lat"])
        & (nodes_wgs84.geometry.y <= bounds["max_lat"])
    )
    filtered = nodes[mask].copy()
    filtered_wgs84 = nodes_wgs84[mask].copy()
    filtered["lon"] = filtered_wgs84.geometry.x.values
    filtered["lat"] = filtered_wgs84.geometry.y.values
    return filtered


def _load_lion_segments() -> gpd.GeoDataFrame:
    minx, miny = _TRANSFORM_4326_TO_2263.transform(
        LOWER_MANHATTAN_BOUNDS["min_lon"], LOWER_MANHATTAN_BOUNDS["min_lat"]
    )
    maxx, maxy = _TRANSFORM_4326_TO_2263.transform(
        LOWER_MANHATTAN_BOUNDS["max_lon"], LOWER_MANHATTAN_BOUNDS["max_lat"]
    )
    return read_dataframe(
        PATHS.lion_gdb_path,
        layer="lion",
        columns=[
            "Street",
            "NodeIDFrom",
            "NodeIDTo",
            "FeatureTyp",
            "RB_Layer",
            "NonPed",
            "LBoro",
            "RBoro",
            "StreetWidth_Max",
        ],
        bbox=(minx, miny, maxx, maxy),
    )


def _is_usable_street(street: object) -> bool:
    if not isinstance(street, str):
        return False

    cleaned = street.strip()
    if not cleaned:
        return False

    banned_tokens = [
        "BOUNDARY",
        "BIKE PATH",
        "PEDESTRIAN",
        "FDR DRIVE",
        "RAMP",
        "SLIP",
        "EXIT",
        "ENTRANCE",
        "LINE",
    ]
    return not any(token in cleaned.upper() for token in banned_tokens)


def _group_segments_by_street(node_id: int, segments: List[dict], node_point: Point) -> List[Tuple[str, List[dict], float]]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for segment in segments:
        grouped[segment["street"]].append(segment)

    ranked: List[Tuple[str, List[dict], float]] = []
    for street_name, street_segments in grouped.items():
        strength = sum(segment["width"] for segment in street_segments) + len(street_segments) * 4.0
        ranked.append((street_name, street_segments, strength))

    ranked.sort(key=lambda item: item[2], reverse=True)
    return ranked


def _segment_heading(node_point: Point, geometry) -> float:
    coords = list(geometry.coords) if geometry.geom_type == "LineString" else list(geometry.geoms[0].coords)
    start = coords[0]
    end = coords[-1]
    distance_to_start = _distance(node_point.x, node_point.y, start[0], start[1])
    distance_to_end = _distance(node_point.x, node_point.y, end[0], end[1])
    other = end if distance_to_start <= distance_to_end else start
    dx = other[0] - node_point.x
    dy = other[1] - node_point.y
    angle = math.degrees(math.atan2(dy, dx))
    heading = angle % 180.0
    return heading


def _mean_heading(headings: Iterable[float]) -> float:
    radians = [math.radians(heading * 2.0) for heading in headings]
    if not radians:
        return 90.0

    sin_sum = sum(math.sin(value) for value in radians)
    cos_sum = sum(math.cos(value) for value in radians)
    mean = math.degrees(math.atan2(sin_sum, cos_sum)) / 2.0
    return mean % 180.0


def _format_street_name(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split())


def _distance(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)
