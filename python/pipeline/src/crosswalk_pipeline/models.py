from __future__ import annotations

from dataclasses import asdict, dataclass
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

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)
