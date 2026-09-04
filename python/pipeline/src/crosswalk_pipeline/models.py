from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List


@dataclass
class CandidateRecord:
    id: str
    intersection_label: str
    leg_label: str
    lat: float
    lon: float
    year: int
    paint_missing_ratio: float
    stripe_break_ratio: float
    contrast_score: float
    occlusion_penalty: float
    school_zone: bool
    pavement_marking_311_count_since_2020: int
    heading_degrees: float
    secondary_heading_degrees: float | None = None
    street_width_ft: float = 0.0
    approach_street_count: int = 2
    neighborhood_id: str = ""
    neighborhood_name: str = ""
    borough: str = ""
    pedestrian_crash_count: int = 0

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class ExportRecord:
    id: str
    intersection_label: str
    leg_label: str
    lat: float
    lon: float
    year: int
    severity_score: int
    confidence_score: float
    rank_score: float
    reason_tags: List[str]
    school_zone: bool
    pavement_marking_311_count_since_2020: int
    matched_311_complaints: List[Dict[str, str]]
    image_url: str
    thumbnail_url: str
    google_maps_url: str
    model_score: float = 0.0
    heuristic_score: float = 0.0
    neighborhood: str = ""
    neighborhood_id: str = ""
    borough: str = ""
    priority_reason: str = ""
    pedestrian_crash_count: int = 0
    top_features: List[Dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def candidate_from_dict(item: dict) -> CandidateRecord:
    secondary = item.get("secondary_heading_degrees")
    paint = item.get("paint_missing_ratio")
    stripe = item.get("stripe_break_ratio")
    contrast = item.get("contrast_score")
    occlusion = item.get("occlusion_penalty")
    return CandidateRecord(
        id=str(item["id"]),
        intersection_label=str(item["intersection_label"]),
        # Live candidates are LION/fixture intersection nodes, not crosswalk polygons.
        leg_label=str(item.get("leg_label") or "intersection node"),
        lat=float(item["lat"]),
        lon=float(item["lon"]),
        year=int(item.get("year") or 2024),
        paint_missing_ratio=float(paint) if paint is not None else 0.0,
        stripe_break_ratio=float(stripe) if stripe is not None else 0.0,
        contrast_score=float(contrast) if contrast is not None else 0.0,
        occlusion_penalty=float(occlusion) if occlusion is not None else 0.0,
        school_zone=bool(item.get("school_zone")),
        pavement_marking_311_count_since_2020=int(item.get("pavement_marking_311_count_since_2020") or 0),
        heading_degrees=float(item.get("heading_degrees") or 90.0),
        secondary_heading_degrees=float(secondary) if secondary is not None else None,
        street_width_ft=float(item.get("street_width_ft") or 0.0),
        approach_street_count=int(item.get("approach_street_count") or 2),
        neighborhood_id=str(item.get("neighborhood_id") or ""),
        neighborhood_name=str(item.get("neighborhood_name") or ""),
        borough=str(item.get("borough") or ""),
        pedestrian_crash_count=int(item.get("pedestrian_crash_count") or 0),
    )
