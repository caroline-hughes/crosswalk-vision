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
from .gis_join import (
    assign_neighborhoods,
    crash_counts_from_join,
    join_events_to_candidates,
    load_json_records,
    points_within_radius,
)
from .io_utils import write_json
from .models import CandidateRecord, candidate_from_dict
from .soda import fetch_soda_records

LION_VIEW_URL = "https://data.cityofnewyork.us/api/views/2v4z-66xt.json"
LION_DOWNLOAD_FALLBACK = (
    "https://data.cityofnewyork.us/api/views/2v4z-66xt/files/"
    "30298730-5064-447c-8c39-a3981409d9b3?download=1"
)
SCHOOL_LOCATIONS_URL = "https://data.cityofnewyork.us/resource/wg9x-4ke6.json"
PEDESTRIAN_CRASH_RESOURCE = "https://data.cityofnewyork.us/resource/h9gi-nx95.json"
PEDESTRIAN_CRASH_SELECT = (
    "collision_id,crash_date,latitude,longitude,on_street_name,off_street_name,"
    "cross_street_name,number_of_pedestrians_injured,number_of_pedestrians_killed,borough"
)
PEDESTRIAN_CRASH_WHERE = (
    "latitude >= 40.49 AND latitude <= 40.92 AND longitude >= -74.27 AND longitude <= -73.70 "
    "AND (number_of_pedestrians_injured > 0 OR number_of_pedestrians_killed > 0) "
    "AND crash_date >= '2020-01-01T00:00:00'"
)
NTA_GEOJSON_URL = (
    "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/"
    "NYC_Neighborhood_Tabulation_Areas_2020/FeatureServer/0/query"
    "?where=1%3D1&outFields=NTA2020,NTAName,NTAAbbrev,BoroName,BoroCode"
    "&outSR=4326&f=geojson"
)
PAVEMENT_311_RESOURCE = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
PAVEMENT_311_SELECT = "unique_key,created_date,complaint_type,descriptor,latitude,longitude,incident_address,borough"
PAVEMENT_311_WHERE = (
    "complaint_type='Street Condition' AND descriptor in('Line/Marking - Faded','Line/Marking - After Repaving') "
    "AND created_date >= '2020-01-01T00:00:00' AND latitude is not null AND longitude is not null "
    "AND latitude >= 40.49 AND latitude <= 40.92 AND longitude >= -74.27 AND longitude <= -73.70"
)
PAVEMENT_311_ORDER = "unique_key"

# Leftover Lower Manhattan pilot bbox (imagery only; not used for citywide ranking).
LOWER_MANHATTAN_BOUNDS = {
    "min_lon": -74.02,
    "max_lon": -73.99,
    "min_lat": 40.7000,
    "max_lat": 40.7205,
}

NYC_BOUNDS = {
    "min_lon": -74.27,
    "max_lon": -73.70,
    "min_lat": 40.49,
    "max_lat": 40.92,
}

NYC_LABEL = "New York City (five boroughs)"
LOWER_MANHATTAN_LABEL = NYC_LABEL  # kept for import compatibility with older CLI
SCHOOL_PROXIMITY_FT = 800.0
SCHOOL_LOCATION_CATEGORIES = {"Elementary", "K-8", "Early Childhood"}
PLOT_PERCENTILE = 95.0
PLOT_MAX = 2000
PLOT_BOROUGH_FLOOR = 40
RECENT_311_CAP = 3
LION_STREET_FEATURE_TYPES = {"0", "A", "W"}

_TRANSFORM_4326_TO_2263 = Transformer.from_crs(4326, 2263, always_xy=True)


@dataclass
class LiveSourceVersions:
    lion: str = "NYC LION (CSCL street network, all five boroughs)"
    imagery: str = (
        "Spring 2024 NYS ITS ortho (wms/2024) for the plotted in-need set. "
        "2025 does not cover NYC; no 2026 MapServer."
    )
    school_zones: str = "DOE school points: elementary/K-8 within 800 ft (citywide)"
    service_requests_311: str = "NYC Open Data 311 pavement-marking complaints since 2020 (citywide)"
    vision_zero_crashes: str = (
        "NYPD Motor Vehicle Collisions pedestrian injured/killed since 2020 (h9gi-nx95, citywide)"
    )
    neighborhoods: str = "NYC 2020 Neighborhood Tabulation Areas (all boroughs)"


def ensure_live_sources() -> LiveSourceVersions:
    PATHS.raw_dir.mkdir(parents=True, exist_ok=True)
    versions = LiveSourceVersions()

    if not PATHS.lion_zip_path.exists():
        try:
            _download_file(_resolve_lion_url(), PATHS.lion_zip_path)
        except Exception:
            versions.lion = "fixture candidates (LION download failed)"

    if PATHS.lion_zip_path.exists() and not PATHS.lion_gdb_path.exists():
        PATHS.lion_unzipped_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(PATHS.lion_zip_path, "r") as archive:
            archive.extractall(PATHS.lion_unzipped_dir)

    if PATHS.lion_gdb_path.exists():
        versions.lion = "NYC LION gdb (citywide intersection nodes)"

    try:
        _fetch_school_locations(PATHS.school_locations_path)
        versions.school_zones = (
            f"DOE elementary/K-8 points ({_json_len(PATHS.school_locations_path)} schools, citywide, 800 ft)"
        )
    except Exception:
        fixture = PATHS.fixtures_dir / "school_locations.json"
        if fixture.exists() and (not PATHS.school_locations_path.exists() or PATHS.school_locations_path.stat().st_size == 0):
            shutil.copyfile(fixture, PATHS.school_locations_path)
            versions.school_zones = "fixture DOE elementary/K-8 points (800 ft)"
        elif PATHS.school_locations_path.exists():
            versions.school_zones = f"committed DOE points ({_json_len(PATHS.school_locations_path)} schools)"
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
        write_json(pavement_311_path, complaints, indent=None)
        versions.service_requests_311 = (
            f"NYC 311 faded/after-repaving line markings since 2020 ({len(complaints)} rows, SODA paginated, citywide)"
        )
    except Exception:
        fixture = PATHS.fixtures_dir / "pavement_marking_311.json"
        if fixture.exists() and (not pavement_311_path.exists() or pavement_311_path.stat().st_size == 0):
            shutil.copyfile(fixture, pavement_311_path)
        versions.service_requests_311 = "fixture 311 pavement-marking complaints"

    try:
        crashes = fetch_soda_records(
            PEDESTRIAN_CRASH_RESOURCE,
            select=PEDESTRIAN_CRASH_SELECT,
            where=PEDESTRIAN_CRASH_WHERE,
            order="collision_id",
        )
        write_json(PATHS.crashes_path, crashes, indent=None)
        versions.vision_zero_crashes = (
            f"NYPD pedestrian injured/killed since 2020 ({len(crashes)} rows, citywide)"
        )
    except Exception:
        fixture = PATHS.fixtures_dir / "pedestrian_crashes.json"
        if not PATHS.crashes_path.exists() or PATHS.crashes_path.stat().st_size == 0:
            if fixture.exists():
                shutil.copyfile(fixture, PATHS.crashes_path)
        versions.vision_zero_crashes = "fixture NYPD pedestrian crash events since 2020"

    if not _download_json_with_fallback(
        NTA_GEOJSON_URL,
        PATHS.nta_geojson_path,
        PATHS.fixtures_dir / "nta_citywide.geojson",
        PATHS.nta_geojson_path,
    ):
        lm_fixture = PATHS.fixtures_dir / "nta_lower_manhattan.geojson"
        if PATHS.nta_geojson_path.exists() and PATHS.nta_geojson_path.stat().st_size > 0:
            versions.neighborhoods = "committed 2020 NTAs"
        elif lm_fixture.exists():
            shutil.copyfile(lm_fixture, PATHS.nta_geojson_path)
            versions.neighborhoods = "fixture 2020 NTAs (Lower Manhattan leftover)"
        else:
            versions.neighborhoods = "NTA download failed"

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
    nodes = _load_citywide_nodes(read_dataframe)

    node_ids = set(nodes["NODEID"].astype(int).tolist())
    lion["NodeIDFrom"] = pd.to_numeric(lion["NodeIDFrom"], errors="coerce").fillna(0).astype(int)
    lion["NodeIDTo"] = pd.to_numeric(lion["NodeIDTo"], errors="coerce").fillna(0).astype(int)
    lion["LBoro"] = pd.to_numeric(lion["LBoro"], errors="coerce").fillna(0).astype(int)
    lion["RBoro"] = pd.to_numeric(lion["RBoro"], errors="coerce").fillna(0).astype(int)
    lion = lion[(lion["LBoro"].between(1, 5)) | (lion["RBoro"].between(1, 5))].copy()
    if "FeatureTyp" in lion.columns:
        lion = lion[lion["FeatureTyp"].astype(str).isin(LION_STREET_FEATURE_TYPES)].copy()
    if "NonPed" in lion.columns:
        lion = lion[lion["NonPed"].astype(str).str.strip() != "V"].copy()
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
    candidates: List[CandidateRecord] = []

    for node_id, segments in segments_by_node.items():
        grouped = _group_segments_by_street(node_id, segments, node_lookup[node_id].geometry)
        if len(grouped) < 2:
            continue
        primary = grouped[:2]
        node = node_lookup[node_id]
        intersection_streets = [group[0] for group in grouped[:3]]
        intersection_label = " & ".join(_format_street_name(name) for name in intersection_streets[:2])
        lat = float(node.lat)
        lon = float(node.lon)
        primary_heading = _mean_heading(
            [_segment_heading(node.geometry, segment["geometry"]) for segment in primary[0][1]]
        )
        secondary_heading = _mean_heading(
            [_segment_heading(node.geometry, segment["geometry"]) for segment in primary[1][1]]
        )
        widths = [float(segment["width"]) for group in primary for segment in group[1]]
        candidates.append(
            CandidateRecord(
                id=f"nyc-{node_id}",
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
                approach_street_count=int(len(grouped)),
            )
        )

    return candidates


def _load_fixture_candidates() -> List[CandidateRecord]:
    for name in ("citywide_candidates.json", "expanded_candidates.json"):
        path = PATHS.fixtures_dir / name
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            return [candidate_from_dict(item) for item in payload]
    return []


def annotate_school_zones(candidates: List[CandidateRecord]) -> Dict[str, bool]:
    """True if the node is within 800 ft of an elementary/K-8 school."""
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


def annotate_311_details(
    candidates: List[CandidateRecord], *, max_per_node: int = 8
) -> Dict[str, List[Dict[str, str]]]:
    pavement_311_path = PATHS.raw_dir / "pavement_marking_311.json"
    empty = {candidate.id: [] for candidate in candidates}
    if not pavement_311_path.exists():
        return empty
    complaints = pd.read_json(pavement_311_path)
    if complaints.empty:
        return empty

    events = complaints.to_dict(orient="records")
    matched_events = join_events_to_candidates(
        [candidate.to_dict() for candidate in candidates],
        events,
        radius_ft=150.0,
        lat_field="latitude",
        lon_field="longitude",
    )
    matched: Dict[str, List[Dict[str, str]]] = {candidate.id: [] for candidate in candidates}
    for candidate_id, rows in matched_events.items():
        formatted: List[Dict[str, str]] = []
        for complaint in rows:
            unique_key = str(complaint.get("unique_key") or "").strip()
            formatted.append(
                {
                    "unique_key": unique_key,
                    "created_date": str(complaint.get("created_date") or ""),
                    "descriptor": str(complaint.get("descriptor") or ""),
                    "incident_address": str(complaint.get("incident_address") or ""),
                    "url": (
                        "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
                        f"?$select=unique_key,created_date,closed_date,agency,agency_name,"
                        f"complaint_type,descriptor,location_type,incident_address,"
                        f"status,resolution_description"
                        f"&$where=unique_key=%27{unique_key}%27"
                    ),
                }
            )
        formatted.sort(key=lambda entry: entry["created_date"], reverse=True)
        matched[candidate_id] = formatted[:max_per_node]
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
        PATHS.nta_geojson_path if PATHS.nta_geojson_path.exists() else PATHS.fixtures_dir / "nta_citywide.geojson"
    )
    if not nta_path.exists():
        nta_path = PATHS.fixtures_dir / "nta_lower_manhattan.geojson"
    if not nta_path.exists():
        return {
            candidate.id: {
                "neighborhood_id": "UNKNOWN",
                "neighborhood_name": "Unknown",
                "borough": "Unknown",
            }
            for candidate in candidates
        }
    return assign_neighborhoods([candidate.to_dict() for candidate in candidates], nta_path)


def select_plottable(scored_records: List[dict]) -> List[dict]:
    """Cap the map to a readable 'in need' set: top percentile, plus a per-borough floor."""
    if not scored_records:
        return []
    scores = sorted((float(row.get("model_score") or 0.0) for row in scored_records), reverse=True)
    percentile_index = min(len(scores) - 1, max(0, int(math.floor(len(scores) * (1.0 - PLOT_PERCENTILE / 100.0)))))
    threshold = scores[percentile_index]
    ranked = sorted(
        scored_records,
        key=lambda row: (
            float(row.get("model_score") or 0.0),
            int(row.get("pedestrian_crash_count") or 0),
            float(row.get("heuristic_score") or 0.0),
        ),
        reverse=True,
    )
    ranked = [
        row
        for row in ranked
        if "unnamed" not in str(row.get("intersection_label") or "").lower()
    ]
    selected: List[dict] = []
    selected_ids: set[str] = set()
    for row in ranked:
        if float(row.get("model_score") or 0.0) < threshold:
            break
        selected.append(row)
        selected_ids.add(str(row["id"]))
        if len(selected) >= PLOT_MAX:
            break

    by_borough: Dict[str, List[dict]] = defaultdict(list)
    for row in ranked:
        by_borough[str(row.get("borough") or "Unknown")].append(row)
    for _borough, rows in by_borough.items():
        have = sum(1 for row in selected if str(row.get("borough") or "Unknown") == _borough)
        if have >= PLOT_BOROUGH_FLOOR:
            continue
        for row in rows:
            if str(row["id"]) in selected_ids:
                continue
            selected.append(row)
            selected_ids.add(str(row["id"]))
            have += 1
            if have >= PLOT_BOROUGH_FLOOR:
                break

    selected.sort(
        key=lambda row: (
            float(row.get("model_score") or 0.0),
            int(row.get("pedestrian_crash_count") or 0),
        ),
        reverse=True,
    )
    return selected


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
        if not (NYC_BOUNDS["min_lat"] <= lat <= NYC_BOUNDS["max_lat"] and NYC_BOUNDS["min_lon"] <= lon <= NYC_BOUNDS["max_lon"]):
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
    write_json(destination, filtered, indent=None)


def _resolve_lion_url() -> str:
    try:
        response = requests.get(LION_VIEW_URL, timeout=60)
        response.raise_for_status()
        blob_id = response.json().get("blobId")
        if blob_id:
            return f"https://data.cityofnewyork.us/api/views/2v4z-66xt/files/{blob_id}?download=1"
    except Exception:
        pass
    return LION_DOWNLOAD_FALLBACK


def _download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=180)
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


def _load_citywide_nodes(read_dataframe):
    nodes = read_dataframe(PATHS.lion_gdb_path, layer="node", columns=["NODEID", "VIntersect"])
    nodes_wgs84 = nodes.to_crs(4326)
    bounds = NYC_BOUNDS
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
        where="FeatureTyp IN ('0','A','W')",
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
        " LINE",
        "RAILROAD",
        "SHORELINE",
        "PIER ",
        "FERRY",
    ]
    upper = cleaned.upper()
    if upper.startswith("UNNAMED") or " UNNAMED" in upper:
        return False
    return not any(token in upper for token in banned_tokens)


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


def _json_len(path: Path) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return len(payload) if isinstance(payload, list) else 0
    except Exception:
        return 0
