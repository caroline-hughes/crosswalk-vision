from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

from crosswalk_scoring import HeuristicCrosswalkScorer, ScoringInput

from .artifact_store import LocalArtifactStore
from .config import PATHS
from .imagery import create_crosswalk_crop, create_thumbnail
from .io_utils import read_json, write_json
from .models import CandidateRecord, ExportRecord


def fetch_sources() -> None:
    manifest = {
        "generated_at": _utc_now(),
        "sources": {
            "imagery": {
                "name": "2024 NYS Orthoimagery",
                "url": "https://gis.ny.gov/new-york-city-orthoimagery-downloads"
            },
            "lion": {
                "name": "NYC LION Street Base Map",
                "url": "https://catalog.data.gov/dataset/lion"
            },
            "service_requests_311": {
                "name": "NYC 311 Pavement Marking Requests",
                "url": "https://portal.311.nyc.gov/article/?kanumber=KA-01100"
            },
            "school_zones": {
                "name": "NYC school-zone enrichment",
                "url": "https://data.cityofnewyork.us/"
            }
        },
        "note": "V1 uses fixture candidates locally. Replace manifests with live fetchers when the data connectors are ready."
    }
    write_json(PATHS.raw_dir / "source_manifest.json", manifest)


def prepare_candidates() -> None:
    fixture_path = PATHS.fixtures_dir / "lower_manhattan_candidates.json"
    candidates = [_candidate_from_dict(item) for item in read_json(fixture_path)]
    write_json(PATHS.processed_dir / "candidates.json", [candidate.to_dict() for candidate in candidates])


def enrich_candidates() -> None:
    candidates = [_candidate_from_dict(item) for item in read_json(PATHS.processed_dir / "candidates.json")]
    enriched = []
    for candidate in candidates:
        enriched.append(
            {
                **candidate.to_dict(),
                "google_maps_url": f"https://www.google.com/maps?q={candidate.lat},{candidate.lon}"
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

    scored_records.sort(key=lambda record: record["rank_score"], reverse=True)
    write_json(PATHS.processed_dir / "scored_candidates.json", scored_records)


def export_snapshot() -> None:
    scored_records = read_json(PATHS.processed_dir / "scored_candidates.json")
    store = LocalArtifactStore()
    export_records: List[ExportRecord] = []

    for item in scored_records:
        candidate = _candidate_from_dict(item)
        crop_bytes = create_crosswalk_crop(candidate)
        thumb_bytes = create_thumbnail(candidate)
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
                image_url=image_url,
                thumbnail_url=thumbnail_url,
                google_maps_url=item["google_maps_url"],
            )
        )

    crosswalk_payload = [record.to_dict() for record in export_records]
    meta_payload = {
        "build_timestamp": _utc_now(),
        "source_versions": {
            "imagery": "NYS orthoimagery 2024",
            "lion": "NYC LION current",
            "service_requests_311": "NYC Open Data pavement-marking complaint snapshot",
            "school_zones": "NYC school-zone snapshot"
        },
        "pilot_boundary": "Lower Manhattan south of Canal Street",
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
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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
