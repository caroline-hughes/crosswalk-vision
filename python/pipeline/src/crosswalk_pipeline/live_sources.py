from __future__ import annotations

import json
import math
import shutil
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd
import requests
from pyproj import Transformer
from shapely.geometry import Point

from .config import PATHS
from .gis_join import assign_neighborhoods, crash_counts_from_join, join_events_to_candidates, load_json_records, points_within_radius
from .io_utils import write_json
from .models import CandidateRecord, candidate_from_dict
from .soda import fetch_soda_records

LION_DOWNLOAD_URL = (
    "https://data.cityofnewyork.us/api/views/2v4z-66xt/files/"
    "a3e46353-0b43-4b3b-a4fd-9bb042ccabb7?download=1"
)
SCHOOL_ZONES_CSV_URL = "https://data.cityofnewyork.us/api/views/cmjf-yawu/rows.csv?accessType=DOWNLOAD"
SCHOOL_LOCATIONS_URL = "https://data.cityofnewyork.us/resource/wg9x-4ke6.json"
PEDESTRIAN_CRASH_URL = (
    "https://data.cityofnewyork.us/resource/h9gi-nx95.json"
    "?$select=collision_id,crash_date,latitude,longitude,on_street_name,off_street_name,"
    "cross_street_name,number_of_pedestrians_injured,number_of_pedestrians_killed"
    "&$where=latitude%20%3E=%2040.7000%20AND%20latitude%20%3C=%2040.7205"
    "%20AND%20longitude%20%3E=%20-74.02%20AND%20longitude%20%3C=%20-73.99"
    "%20AND%20(number_of_pedestrians_injured%20%3E%200%20OR%20number_of_pedestrians_killed%20%3E%200)"
    "%20AND%20crash_date%20%3E=%20%272020-01-01T00:00:00%27"
    "&$limit=50000"
)
NTA_GEOJSON_URL = (
    "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/"
    "NYC_Neighborhood_Tabulation_Areas_2020/FeatureServer/0/query"
    "?where=BoroName%3D%27Manhattan%27"
    "&outFields=NTA2020,NTAName,NTAAbbrev"
    "&geometry=-74.02,40.7000,-73.99,40.7205"
    "&geometryType=esriGeometryEnvelope&inSR=4326"
    "&spatialRel=esriSpatialRelIntersects&outSR=4326&f=geojson"
)
# Socrata default page is 100. Never treat a 100-row dump as complete.
PAVEMENT_311_RESOURCE = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
PAVEMENT_311_SELECT = "unique_key,created_date,complaint_type,descriptor,latitude,longitude,incident_address"
PAVEMENT_311_WHERE = (
    "complaint_type='Street Condition' AND descriptor in('Line/Marking - Faded','Line/Marking - After Repaving') "
    "AND created_date >= '2020-01-01T00:00:00' AND latitude is not null AND longitude is not null "
    "AND latitude >= 40.6980 AND latitude <= 40.7230 AND longitude >= -74.022 AND longitude <= -73.987"
)
PAVEMENT_311_ORDER = "unique_key"

LOWER_MANHATTAN_BOUNDS = {
    "min_lon": -74.02,
    "max_lon": -73.99,
    "min_lat": 40.7000,
    "max_lat": 40.7205,
}

LOWER_MANHATTAN_LABEL = "Lower Manhattan south of Canal Street"
MAX_INTERSECTIONS = 60
SHOWCASE_TOP_K = 16
SCHOOL_PROXIMITY_FT = 800.0
SCHOOL_LOCATION_CATEGORIES = {"Elementary", "K-8", "Early Childhood"}

_TRANSFORM_4326_TO_2263 = Transformer.from_crs(4326, 2263, always_xy=True)


@dataclass
class LiveSourceVersions:
    lion: str = "NYC LION 26a"
    imagery: str = "NYS 2024 orthos via ArcGIS MapServer"
    school_zones: str = "DOE school points: elementary/K-8 within 800 ft (not attendance-zone polygons)"
    service_requests_311: str = "NYC Open Data 311 pavement-marking complaints since 2020"
    vision_zero_crashes: str = (
        "NYPD Motor Vehicle Collisions pedestrian injured/killed since 2020 (h9gi-nx95)"
    )
    neighborhoods: str = "NYC 2020 Neighborhood Tabulation Areas"


def ensure_live_sources() -> LiveSourceVersions:
    PATHS.raw_dir.mkdir(parents=True, exist_ok=True)
    versions = LiveSourceVersions()

    if not PATHS.lion_zip_path.exists():
        try:
            _download_file(LION_DOWNLOAD_URL, PATHS.lion_zip_path)
        except Exception:
            versions.lion = "fixture candidates (LION download failed)"

    if PATHS.lion_zip_path.exists() and not PATHS.lion_gdb_path.exists():
        PATHS.lion_unzipped_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(PATHS.lion_zip_path, "r") as archive:
            archive.extractall(PATHS.lion_unzipped_dir)

    if not PATHS.school_locations_path.exists():
        try:
            _fetch_school_locations(PATHS.school_locations_path)
        except Exception:
            fixture = PATHS.fixtures_dir / "school_locations.json"
            if fixture.exists():
                shutil.copyfile(fixture, PATHS.school_locations_path)
                versions.school_zones = "fixture DOE elementary/K-8 points (800 ft)"
            else:
                versions.school_zones = "unavailable (download failed; school_zone=false)"

    pavement_311_path = PATHS.raw_dir / "pavement_marking_311.json"
    try:
        complaints = fetch_soda_records(
            PAVEMENT_311_RESOURCE,
            select=PAVEMENT_311_SELECT,
            where=PAVEMENT_311_WHERE,
            order=PAVEMENT_311_ORDER,
        )
        write_json(pavement_311_path, complaints)
        versions.service_requests_311 = (
            f"NYC 311 faded/after-repaving line markings since 2020 ({len(complaints)} rows, SODA paginated)"
        )
    except Exception:
        fixture = PATHS.fixtures_dir / "pavement_marking_311.json"
        if fixture.exists() and (not pavement_311_path.exists() or pavement_311_path.stat().st_size == 0):
            shutil.copyfile(fixture, pavement_311_path)
        versions.service_requests_311 = "fixture 311 pavement-marking complaints"

    if not _download_json_with_fallback(
        PEDESTRIAN_CRASH_URL,
        PATHS.crashes_path,
        PATHS.fixtures_dir / "pedestrian_crashes.json",
        PATHS.crashes_path,
    ):
        versions.vision_zero_crashes = "fixture NYPD pedestrian crash events since 2020"

    if not _download_json_with_fallback(
        NTA_GEOJSON_URL,
        PATHS.nta_geojson_path,
        PATHS.fixtures_dir / "nta_lower_manhattan.geojson",
        PATHS.nta_geojson_path,
    ):
        versions.neighborhoods = "fixture 2020 NTAs clipped to Lower Manhattan"

    return versions


def build_live_candidates() -> List[CandidateRecord]:
    if PATHS.lion_gdb_path.exists():
        try:
            return _build_lion_candidates()
        except Exception:
            pass
    return _load_fixture_candidates()


def _build_lion_candidates() -> List[CandidateRecord]:
    import geopandas as gpd  # noqa: F401  # imported for side-effect CRS support
    from pyogrio import read_dataframe

    lion = _load_lion_segments(read_dataframe)
    nodes = _load_lower_manhattan_nodes(read_dataframe)

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
    ranked_nodes: List[Tuple[float, int, List[Tuple[str, List[dict], float]], int]] = []

    for node_id, segments in segments_by_node.items():
        grouped = _group_segments_by_street(node_id, segments, node_lookup[node_id].geometry)
        if len(grouped) < 2:
            continue
        primary = grouped[:2]
        score = sum(group[2] for group in primary) + len(grouped) * 10.0
        ranked_nodes.append((score, node_id, primary, len(grouped)))

    ranked_nodes.sort(key=lambda item: item[0], reverse=True)

    candidates: List[CandidateRecord] = []
    for _, node_id, primary_groups, street_count in ranked_nodes[:MAX_INTERSECTIONS]:
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
        widths = [float(segment["width"]) for group in primary_groups for segment in group[1]]
        candidates.append(
            CandidateRecord(
                id=f"lm-live-{node_id}",
                intersection_label=intersection_label,
                leg_label="intersection node",
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
                street_width_ft=max(widths) if widths else 0.0,
                approach_street_count=int(street_count),
            )
        )

    return candidates


def _load_fixture_candidates() -> List[CandidateRecord]:
    path = PATHS.fixtures_dir / "expanded_candidates.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [candidate_from_dict(item) for item in payload]


def annotate_school_zones(candidates: List[CandidateRecord]) -> Dict[str, bool]:
    """True if the node is within 800 ft of an elementary/K-8 school.

    Attendance-zone polygons cover essentially the entire Lower Manhattan bbox, so a
    polygon join makes the School Zone filter a no-op. Proximity to a school building
    is the civic feature that actually varies.
    """
    path = PATHS.school_locations_path
    if not path.exists():
        fallback = PATHS.fixtures_dir / "school_locations.json"
        path = fallback if fallback.exists() else path
    if not path.exists():
        return {candidate.id: False for candidate in candidates}

    schools = json.loads(path.read_text(encoding="utf-8"))
    flagged = points_within_radius(
        [candidate.to_dict() for candidate in candidates],
        schools,
        radius_ft=SCHOOL_PROXIMITY_FT,
        lat_field="latitude",
        lon_field="longitude",
    )
    return flagged


def annotate_311_counts(candidates: List[CandidateRecord]) -> Dict[str, int]:
    details = annotate_311_details(candidates)
    return {candidate_id: len(entries) for candidate_id, entries in details.items()}


def annotate_311_details(candidates: List[CandidateRecord]) -> Dict[str, List[Dict[str, str]]]:
    pavement_311_path = PATHS.raw_dir / "pavement_marking_311.json"
    if not pavement_311_path.exists():
        return {candidate.id: [] for candidate in candidates}
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


def annotate_crashes(candidates: List[CandidateRecord]) -> Dict[str, int]:
    crash_path = PATHS.crashes_path if PATHS.crashes_path.exists() else PATHS.fixtures_dir / "pedestrian_crashes.json"
    if not crash_path.exists():
        return {candidate.id: 0 for candidate in candidates}
    events = load_json_records(crash_path)
    matched = join_events_to_candidates(
        [candidate.to_dict() for candidate in candidates],
        events,
        lat_field="latitude",
        lon_field="longitude",
    )
    return crash_counts_from_join(matched)


def annotate_neighborhoods(candidates: List[CandidateRecord]) -> Dict[str, Dict[str, str]]:
    nta_path = (
        PATHS.nta_geojson_path if PATHS.nta_geojson_path.exists() else PATHS.fixtures_dir / "nta_lower_manhattan.geojson"
    )
    if not nta_path.exists():
        return {
            candidate.id: {"neighborhood_id": "UNKNOWN", "neighborhood_name": "Unknown"}
            for candidate in candidates
        }
    return assign_neighborhoods([candidate.to_dict() for candidate in candidates], nta_path)


def _fetch_school_locations(destination: Path) -> None:
    records = fetch_soda_records(
        SCHOOL_LOCATIONS_URL,
        select=(
            "fiscal_year,system_code,location_name,location_category_description,"
            "grades_text,status_descriptions,latitude,longitude,nta_name"
        ),
        where="system_code is not null",
        order="system_code",
    )
    years = sorted({str(row.get("fiscal_year") or "") for row in records if row.get("fiscal_year")})
    latest = years[-1] if years else ""
    filtered = []
    for row in records:
        if latest and str(row.get("fiscal_year") or "") != latest:
            continue
        if str(row.get("status_descriptions") or "").lower() != "open":
            continue
        if str(row.get("location_category_description") or "") not in SCHOOL_LOCATION_CATEGORIES:
            continue
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (40.695 <= lat <= 40.725 and -74.025 <= lon <= -73.985):
            continue
        filtered.append(
            {
                "system_code": row.get("system_code"),
                "location_name": row.get("location_name"),
                "location_category_description": row.get("location_category_description"),
                "grades_text": row.get("grades_text"),
                "latitude": lat,
                "longitude": lon,
                "nta_name": row.get("nta_name"),
            }
        )
    write_json(destination, filtered)
    fixture = PATHS.fixtures_dir / "school_locations.json"
    if fixture.resolve() != destination.resolve():
        write_json(fixture, filtered)


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


def _download_json_with_fallback(
    url: str,
    destination: Path,
    fixture_path: Path,
    _already: Path | None = None,
) -> bool:
    try:
        _download_json(url, destination)
        return True
    except Exception:
        if destination.exists() and destination.stat().st_size > 0:
            return False
        if fixture_path.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            if fixture_path.resolve() != destination.resolve():
                shutil.copyfile(fixture_path, destination)
        return False


def _load_lower_manhattan_nodes(read_dataframe) :
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


def _load_lion_segments(read_dataframe):
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
