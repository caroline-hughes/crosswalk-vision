from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

from crosswalk_scoring import HeuristicCrosswalkScorer, ScoringInput

from .artifact_store import LocalArtifactStore
from .config import PATHS
from .io_utils import read_json, write_json
from .live_imagery import fetch_and_analyze_candidate_image
from .live_sources import (
    LOWER_MANHATTAN_LABEL,
    LiveSourceVersions,
    annotate_311_counts,
    annotate_311_details,
    annotate_school_zones,
    build_live_candidates,
    ensure_live_sources,
)
from .models import CandidateRecord, ExportRecord


def fetch_sources() -> None:
    versions = ensure_live_sources()
    manifest = {
        "generated_at": _utc_now(),
        "sources": {
            "imagery": {
                "name": "2024 NYS Orthoimagery",
                "url": "https://orthos.its.ny.gov/arcgis/rest/services/wms/2024/MapServer"
            },
            "lion": {
                "name": "NYC LION Street Base Map",
                "url": "https://data.cityofnewyork.us/api/views/2v4z-66xt/files/a3e46353-0b43-4b3b-a4fd-9bb042ccabb7?download=1"
            },
            "service_requests_311": {
                "name": "NYC 311 Pavement Marking Requests",
                "url": "https://portal.311.nyc.gov/article/?kanumber=KA-01100"
            },
            "school_zones": {
                "name": "NYC school-zone enrichment",
                "url": "https://data.cityofnewyork.us/api/views/cmjf-yawu/rows.csv?accessType=DOWNLOAD"
            }
        },
        "source_versions": {
            "imagery": versions.imagery,
            "lion": versions.lion,
            "service_requests_311": versions.service_requests_311,
            "school_zones": versions.school_zones,
        },
        "note": "Pipeline now downloads LION and school-zone sources locally and fetches imagery from the live 2024 NYS ArcGIS service."
    }
    write_json(PATHS.raw_dir / "source_manifest.json", manifest)


def prepare_candidates() -> None:
    ensure_live_sources()
    candidates = build_live_candidates()
    write_json(PATHS.processed_dir / "candidates.json", [candidate.to_dict() for candidate in candidates])


def enrich_candidates() -> None:
    candidates = [_candidate_from_dict(item) for item in read_json(PATHS.processed_dir / "candidates.json")]
    school_zone_lookup = annotate_school_zones(candidates)
    complaint_detail_lookup = annotate_311_details(candidates)
    complaint_count_lookup = annotate_311_counts(candidates)
    enriched = []
    for candidate in candidates:
        try:
            metrics = fetch_and_analyze_candidate_image(candidate)
        except Exception:
            continue
        enriched.append(
            {
                **candidate.to_dict(),
                "paint_missing_ratio": metrics.paint_missing_ratio,
                "stripe_break_ratio": metrics.stripe_break_ratio,
                "contrast_score": metrics.contrast_score,
                "occlusion_penalty": metrics.occlusion_penalty,
                "school_zone": school_zone_lookup.get(candidate.id, False),
                "pavement_marking_311_count_since_2020": complaint_count_lookup.get(candidate.id, 0),
                "matched_311_complaints": complaint_detail_lookup.get(candidate.id, []),
                "google_maps_url": f"https://www.google.com/maps?q={candidate.lat},{candidate.lon}",
                "processed_image_path": metrics.image_path,
                "processed_thumbnail_path": metrics.thumbnail_path,
            }
        )
    write_json(PATHS.processed_dir / "enriched_candidates.json", enriched)


def score_candidates() -> None:
    scorer = HeuristicCrosswalkScorer(confidence_floor=0.55)
    enriched = read_json(PATHS.processed_dir / "enriched_candidates.json")
    scored_records: List[dict] = []

    for item in enriched:
        candidate = _candidate_from_dict(item)
        scored = scorer.score(
            ScoringInput(
                id=candidate.id,
                paint_missing_ratio=candidate.paint_missing_ratio,
                stripe_break_ratio=candidate.stripe_break_ratio,
                contrast_score=candidate.contrast_score,
                occlusion_penalty=candidate.occlusion_penalty,
                school_zone=candidate.school_zone,
                pavement_marking_311_count_since_2020=candidate.pavement_marking_311_count_since_2020,
            )
        )

        if not scorer.should_include(scored):
            continue

        scored_records.append(
            {
                **item,
                "severity_score": scored.severity_score,
                "confidence_score": scored.confidence_score,
                "rank_score": scored.rank_score,
                "reason_tags": scored.reason_tags,
            }
        )

    scored_records.sort(
        key=lambda record: (
            record["severity_score"],
            record["pavement_marking_311_count_since_2020"],
            record["confidence_score"],
        ),
        reverse=True,
    )
    write_json(PATHS.processed_dir / "scored_candidates.json", scored_records)


def export_snapshot() -> None:
    scored_records = read_json(PATHS.processed_dir / "scored_candidates.json")
    store = LocalArtifactStore()
    export_records: List[ExportRecord] = []

    _clear_directory(PATHS.export_dir / "images")
    _clear_directory(PATHS.web_images_dir)

    for item in scored_records:
        candidate = _candidate_from_dict(item)
        crop_bytes = Path(item["processed_image_path"]).read_bytes()
        thumb_bytes = Path(item["processed_thumbnail_path"]).read_bytes()
        image_url = store.write_crop(candidate.id, crop_bytes)
        thumbnail_url = store.write_thumbnail(candidate.id, thumb_bytes)
        export_records.append(
            ExportRecord(
                id=candidate.id,
                intersection_label=candidate.intersection_label,
                leg_label=candidate.leg_label,
                lat=candidate.lat,
                lon=candidate.lon,
                year=candidate.year,
                severity_score=item["severity_score"],
                confidence_score=item["confidence_score"],
                rank_score=item["rank_score"],
                reason_tags=item["reason_tags"],
                school_zone=candidate.school_zone,
                pavement_marking_311_count_since_2020=candidate.pavement_marking_311_count_since_2020,
                matched_311_complaints=item.get("matched_311_complaints", []),
                image_url=image_url,
                thumbnail_url=thumbnail_url,
                google_maps_url=item["google_maps_url"],
            )
        )

    crosswalk_payload = [record.to_dict() for record in export_records]
    meta_payload = {
        "build_timestamp": _utc_now(),
        "source_versions": {
            "imagery": LiveSourceVersions.imagery,
            "lion": LiveSourceVersions.lion,
            "service_requests_311": LiveSourceVersions.service_requests_311,
            "school_zones": LiveSourceVersions.school_zones,
        },
        "pilot_boundary": LOWER_MANHATTAN_LABEL,
        "total_records": len(crosswalk_payload)
    }

    store.write_export("crosswalks.json", json.dumps(crosswalk_payload, indent=2).encode("utf-8"))
    store.write_export("meta.json", json.dumps(meta_payload, indent=2).encode("utf-8"))


def build_all() -> None:
    fetch_sources()
    prepare_candidates()
    enrich_candidates()
    score_candidates()
    export_snapshot()


def _candidate_from_dict(item: dict) -> CandidateRecord:
    return CandidateRecord(
        id=item["id"],
        intersection_label=item["intersection_label"],
        leg_label=item["leg_label"],
        lat=float(item["lat"]),
        lon=float(item["lon"]),
        year=int(item["year"]),
        paint_missing_ratio=float(item["paint_missing_ratio"]),
        stripe_break_ratio=float(item["stripe_break_ratio"]),
        contrast_score=float(item["contrast_score"]),
        occlusion_penalty=float(item["occlusion_penalty"]),
        school_zone=bool(item["school_zone"]),
        pavement_marking_311_count_since_2020=int(item["pavement_marking_311_count_since_2020"]),
        heading_degrees=float(item["heading_degrees"]),
        secondary_heading_degrees=(
            float(item["secondary_heading_degrees"]) if item.get("secondary_heading_degrees") is not None else None
        ),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clear_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for child in path.iterdir():
        if child.is_file():
            child.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Crosswalk pipeline")
    parser.add_argument(
        "command",
        choices=[
            "fetch_sources",
            "prepare_candidates",
            "enrich_candidates",
            "score_candidates",
            "export_snapshot",
            "build_all",
        ],
    )
    args = parser.parse_args()

    commands = {
        "fetch_sources": fetch_sources,
        "prepare_candidates": prepare_candidates,
        "enrich_candidates": enrich_candidates,
        "score_candidates": score_candidates,
        "export_snapshot": export_snapshot,
        "build_all": build_all,
    }
    commands[args.command]()


if __name__ == "__main__":
    main()
