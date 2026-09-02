from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from crosswalk_scoring import (
    DEFAULT_MODEL_PATH,
    HeuristicCrosswalkScorer,
    LearnedPriorityScorer,
    ScoringInput,
    attach_labels,
    build_priority_reason,
    evaluate_spatial_cv,
    fit_production_scorer,
)

from .artifact_store import LocalArtifactStore
from .config import PATHS
from .io_utils import read_json, write_json
from .live_imagery import fetch_and_analyze_candidate_image
from .live_sources import (
    LOWER_MANHATTAN_LABEL,
    SHOWCASE_TOP_K,
    LiveSourceVersions,
    annotate_311_details,
    annotate_crashes,
    annotate_neighborhoods,
    annotate_school_zones,
    build_live_candidates,
    ensure_live_sources,
)
from .models import CandidateRecord, ExportRecord, candidate_from_dict


def fetch_sources() -> None:
    versions = ensure_live_sources()
    manifest = {
        "generated_at": _utc_now(),
        "pilot_boundary": LOWER_MANHATTAN_LABEL,
        "sources": {
            "imagery": {
                "name": "2024 NYS Orthoimagery",
                "url": "https://orthos.its.ny.gov/arcgis/rest/services/wms/2024/MapServer",
            },
            "lion": {
                "name": "NYC LION Street Base Map",
                "url": "https://data.cityofnewyork.us/api/views/2v4z-66xt/files/a3e46353-0b43-4b3b-a4fd-9bb042ccabb7?download=1",
            },
            "service_requests_311": {
                "name": "NYC 311 faded pavement-marking complaints",
                "url": "https://data.cityofnewyork.us/resource/erm2-nwe9.json",
            },
            "school_zones": {
                "name": "NYC school-zone polygons",
                "url": "https://data.cityofnewyork.us/api/views/cmjf-yawu/rows.csv?accessType=DOWNLOAD",
            },
            "vision_zero_crashes": {
                "name": "NYPD Motor Vehicle Collisions — pedestrian injured or killed",
                "url": "https://data.cityofnewyork.us/resource/h9gi-nx95.json",
                "filter": "bbox Lower Manhattan; crash_date >= 2020-01-01; pedestrians injured or killed > 0",
            },
            "neighborhoods": {
                "name": "NYC 2020 Neighborhood Tabulation Areas",
                "url": "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/NYC_Neighborhood_Tabulation_Areas_2020/FeatureServer/0",
            },
        },
        "source_versions": {
            "imagery": versions.imagery,
            "lion": versions.lion,
            "service_requests_311": versions.service_requests_311,
            "school_zones": versions.school_zones,
            "vision_zero_crashes": versions.vision_zero_crashes,
            "neighborhoods": versions.neighborhoods,
        },
        "note": (
            "Live NYC downloads fall back to committed fixtures when an endpoint fails. "
            "LION gdb is not required for tests; candidate generation uses expanded fixtures "
            "if the gdb is missing. Scoring is a sklearn logistic ranker; the pixel heuristic "
            "is the baseline, not a detector."
        ),
    }
    write_json(PATHS.raw_dir / "source_manifest.json", manifest)


def prepare_candidates() -> None:
    ensure_live_sources()
    candidates = build_live_candidates()
    write_json(PATHS.processed_dir / "candidates.json", [candidate.to_dict() for candidate in candidates])


def enrich_candidates() -> None:
    ensure_live_sources()
    candidates = [candidate_from_dict(item) for item in read_json(PATHS.processed_dir / "candidates.json")]
    school_zone_lookup = annotate_school_zones(candidates)
    complaint_detail_lookup = annotate_311_details(candidates)
    crash_lookup = annotate_crashes(candidates)
    neighborhood_lookup = annotate_neighborhoods(candidates)
    metrics_by_id = _fetch_metrics(candidates)
    enriched = []
    for candidate in candidates:
        neighborhood = neighborhood_lookup.get(
            candidate.id, {"neighborhood_id": "UNKNOWN", "neighborhood_name": "Unknown"}
        )
        item = {
            **candidate.to_dict(),
            "school_zone": school_zone_lookup.get(candidate.id, False),
            "pavement_marking_311_count_since_2020": len(complaint_detail_lookup.get(candidate.id, [])),
            "matched_311_complaints": complaint_detail_lookup.get(candidate.id, []),
            "pedestrian_crash_count": crash_lookup.get(candidate.id, 0),
            "neighborhood_id": neighborhood["neighborhood_id"],
            "neighborhood_name": neighborhood["neighborhood_name"],
            "google_maps_url": f"https://www.google.com/maps?q={candidate.lat},{candidate.lon}",
            "image_metrics_missing": True,
            "paint_missing_ratio": None,
            "stripe_break_ratio": None,
            "contrast_score": None,
            "occlusion_penalty": None,
            "processed_image_path": None,
            "processed_thumbnail_path": None,
        }
        metrics = metrics_by_id.get(candidate.id)
        if metrics is None:
            enriched.append(item)
            continue
        item.update(
            {
                "paint_missing_ratio": metrics.paint_missing_ratio,
                "stripe_break_ratio": metrics.stripe_break_ratio,
                "contrast_score": metrics.contrast_score,
                "occlusion_penalty": metrics.occlusion_penalty,
                "processed_image_path": metrics.image_path,
                "processed_thumbnail_path": metrics.thumbnail_path,
                "image_metrics_missing": False,
            }
        )
        enriched.append(item)
    write_json(PATHS.processed_dir / "enriched_candidates.json", enriched)


def _fetch_metrics(candidates: List[CandidateRecord]) -> dict:
    metrics_by_id: dict = {}

    def _one(candidate: CandidateRecord):
        try:
            return candidate.id, fetch_and_analyze_candidate_image(candidate)
        except Exception:
            return candidate.id, None

    with ThreadPoolExecutor(max_workers=8) as pool:
        for candidate_id, metrics in pool.map(_one, candidates):
            if metrics is not None:
                metrics_by_id[candidate_id] = metrics
    return metrics_by_id


def train_ranker() -> None:
    rows = _labeled_training_rows()
    scorer = fit_production_scorer(rows)
    scorer.save(PATHS.model_artifact_path)
    scorer.save(DEFAULT_MODEL_PATH)
    definition, include_311, labeled = attach_labels(rows)
    write_json(
        PATHS.processed_dir / "ranker_training_meta.json",
        {
            "trained_at": _utc_now(),
            "label_definition": definition,
            "include_311_feature": include_311,
            "n": len(labeled),
            "n_pos": sum(int(row["label"]) for row in labeled),
            "feature_names": scorer.feature_names_,
            "neighborhoods": sorted({str(row.get("neighborhood_id") or "") for row in labeled}),
            "artifact": str(PATHS.model_artifact_path),
        },
    )


def evaluate() -> None:
    rows = _labeled_training_rows()
    report = evaluate_spatial_cv(rows)
    report["generated_at"] = _utc_now()
    write_json(PATHS.eval_json_path, report)
    PATHS.eval_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    PATHS.eval_markdown_path.write_text(_eval_markdown(report), encoding="utf-8")
    store = LocalArtifactStore()
    store.write_export("eval_by_neighborhood.json", json.dumps(report, indent=2).encode("utf-8"))
    store.write_export("eval_by_neighborhood.md", _eval_markdown(report).encode("utf-8"))


def score_candidates() -> None:
    heuristic = HeuristicCrosswalkScorer(confidence_floor=0.0)
    enriched = read_json(PATHS.processed_dir / "enriched_candidates.json")
    learned = _load_or_train_scorer(enriched)
    include_complaints = learned.include_311
    _, _, labeled = attach_labels(enriched)
    model_scores = learned.predict_scores(labeled)
    scored_records: List[dict] = []

    for item, labeled_row, model_score in zip(enriched, labeled, model_scores):
        candidate = candidate_from_dict({**item, **{k: labeled_row.get(k, item.get(k)) for k in item}})
        heuristic_result = heuristic.score(
            ScoringInput(
                id=candidate.id,
                paint_missing_ratio=candidate.paint_missing_ratio,
                stripe_break_ratio=candidate.stripe_break_ratio,
                contrast_score=candidate.contrast_score,
                occlusion_penalty=candidate.occlusion_penalty,
                school_zone=candidate.school_zone,
                pavement_marking_311_count_since_2020=candidate.pavement_marking_311_count_since_2020,
            ),
            include_complaints=include_complaints,
        )
        score_value = float(model_score)
        if not (score_value == score_value) or score_value in (float("inf"), float("-inf")):
            continue
        reason_tags = list(heuristic_result.reason_tags)
        crash_count = int(item.get("pedestrian_crash_count") or 0)
        if crash_count > 0:
            noun = "event" if crash_count == 1 else "events"
            reason_tags.append(f"{crash_count} ped. crash {noun} nearby")
        neighborhood_name = str(item.get("neighborhood_name") or "")
        if neighborhood_name:
            reason_tags.append(neighborhood_name)
        scored_records.append(
            {
                **item,
                "label": labeled_row.get("label"),
                "model_score": round(score_value, 4),
                "heuristic_score": float(heuristic_result.rank_score),
                "severity_score": int(round(score_value * 100)),
                "confidence_score": heuristic_result.confidence_score,
                "rank_score": round(score_value, 4),
                "reason_tags": reason_tags,
                "priority_reason": build_priority_reason({**item, **labeled_row}),
            }
        )

    scored_records.sort(
        key=lambda record: (
            record["model_score"],
            record.get("pedestrian_crash_count") or 0,
            record["heuristic_score"],
        ),
        reverse=True,
    )
    write_json(PATHS.processed_dir / "scored_candidates.json", scored_records)


def export_snapshot() -> None:
    scored_records = read_json(PATHS.processed_dir / "scored_candidates.json")
    store = LocalArtifactStore()
    export_records: List[ExportRecord] = []
    eval_report = {}
    if PATHS.eval_json_path.exists():
        eval_report = read_json(PATHS.eval_json_path)

    _clear_directory(PATHS.export_dir / "images")
    _clear_directory(PATHS.web_images_dir)

    showcase = [
        item
        for item in scored_records
        if item.get("processed_image_path") and Path(item["processed_image_path"]).exists()
    ][:SHOWCASE_TOP_K]

    for item in showcase:
        candidate = candidate_from_dict(item)
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
                severity_score=int(item["severity_score"]),
                confidence_score=float(item["confidence_score"]),
                rank_score=float(item["rank_score"]),
                reason_tags=list(item["reason_tags"]),
                school_zone=candidate.school_zone,
                pavement_marking_311_count_since_2020=candidate.pavement_marking_311_count_since_2020,
                matched_311_complaints=item.get("matched_311_complaints", []),
                image_url=image_url,
                thumbnail_url=thumbnail_url,
                google_maps_url=item["google_maps_url"],
                model_score=float(item["model_score"]),
                heuristic_score=float(item["heuristic_score"]),
                neighborhood=str(item.get("neighborhood_name") or ""),
                neighborhood_id=str(item.get("neighborhood_id") or ""),
                priority_reason=str(item.get("priority_reason") or ""),
                pedestrian_crash_count=int(item.get("pedestrian_crash_count") or 0),
            )
        )

    overall = (eval_report.get("overall") or {}) if isinstance(eval_report, dict) else {}
    learned_auc = (overall.get("learned") or {}).get("roc_auc")
    heuristic_auc = (overall.get("heuristic") or {}).get("roc_auc")
    manifest_path = PATHS.raw_dir / "source_manifest.json"
    source_versions = {
        "imagery": LiveSourceVersions.imagery,
        "lion": LiveSourceVersions.lion,
        "service_requests_311": LiveSourceVersions.service_requests_311,
        "school_zones": LiveSourceVersions.school_zones,
        "vision_zero_crashes": LiveSourceVersions.vision_zero_crashes,
        "neighborhoods": LiveSourceVersions.neighborhoods,
    }
    if manifest_path.exists():
        source_versions.update((read_json(manifest_path).get("source_versions") or {}))
    crosswalk_payload = [record.to_dict() for record in export_records]
    meta_payload = {
        "build_timestamp": _utc_now(),
        "source_versions": source_versions,
        "pilot_boundary": LOWER_MANHATTAN_LABEL,
        "total_records": len(crosswalk_payload),
        "scoring_method": "sklearn logistic ranker (priority); heuristic paint/311 score is the baseline",
        "label_definition": eval_report.get("label_definition", "pedestrian_crash_nearby"),
        "eval_split": eval_report.get("split", "GroupKFold by neighborhood"),
        "eval_n": eval_report.get("n"),
        "eval_n_pos": eval_report.get("n_pos"),
        "eval_learned_auc": learned_auc,
        "eval_heuristic_auc": heuristic_auc,
        "showcase_top_k": SHOWCASE_TOP_K,
        "product_claim": (
            "City-actionable inspection list of Lower Manhattan pedestrian crossings that look "
            "degraded or under-marked relative to Vision Zero crash and 311 complaint burden."
        ),
        "caveat": (
            "Not a crosswalk detector and not a pretty-paint ranking. Crash labels are noisy / "
            "weakly supervised. Metrics use a spatial (neighborhood) split so train and test NTAs "
            "are disjoint. Small n: treat AUC as directional, not a production SLA."
        ),
    }

    store.write_export("crosswalks.json", json.dumps(crosswalk_payload, indent=2).encode("utf-8"))
    store.write_export("meta.json", json.dumps(meta_payload, indent=2).encode("utf-8"))


def build_all() -> None:
    fetch_sources()
    prepare_candidates()
    enrich_candidates()
    train_ranker()
    evaluate()
    score_candidates()
    export_snapshot()


def _labeled_training_rows() -> list[dict]:
    enriched_path = PATHS.processed_dir / "enriched_candidates.json"
    if enriched_path.exists():
        rows = read_json(enriched_path)
        if rows:
            return rows
    fixture_path = PATHS.fixtures_dir / "training_rows.json"
    return read_json(fixture_path)


def _load_or_train_scorer(rows: list[dict]) -> LearnedPriorityScorer:
    for path in (PATHS.model_artifact_path, DEFAULT_MODEL_PATH):
        if path.exists():
            try:
                return LearnedPriorityScorer.load(path)
            except Exception:
                continue
    scorer = fit_production_scorer(rows)
    scorer.save(PATHS.model_artifact_path)
    return scorer


def _eval_markdown(report: dict) -> str:
    overall = report.get("overall") or {}
    learned = overall.get("learned") or {}
    heuristic = overall.get("heuristic") or {}
    lines = [
        "# Spatial evaluation (neighborhood GroupKFold)",
        "",
        f"- Label: `{report.get('label_definition')}`",
        f"- Split: {report.get('split')}",
        f"- n = {report.get('n')}, positives = {report.get('n_pos')}",
        f"- 311 used as a feature: {report.get('include_311_feature')}",
        "",
        report.get("caveat") or "",
        "",
        "## Overall (out-of-fold)",
        "",
        "| scorer | n | positives | ROC-AUC | average precision | precision@5 | precision@10 | Brier |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        _metric_row("learned", learned),
        _metric_row("heuristic baseline", heuristic),
        "",
        "## By neighborhood (test fold for that NTA)",
        "",
        "| NTA | name | n | positives | learned AUC | heuristic AUC | learned P@5 | heuristic P@5 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.get("by_neighborhood") or []:
        learned_n = row.get("learned") or {}
        heuristic_n = row.get("heuristic") or {}
        lines.append(
            "| {id} | {name} | {n} | {pos} | {lauc} | {hauc} | {lp5} | {hp5} |".format(
                id=row.get("neighborhood_id"),
                name=row.get("neighborhood_name"),
                n=learned_n.get("n"),
                pos=learned_n.get("n_pos"),
                lauc=_fmt(learned_n.get("roc_auc")),
                hauc=_fmt(heuristic_n.get("roc_auc")),
                lp5=_fmt(learned_n.get("precision_at_5")),
                hp5=_fmt(heuristic_n.get("precision_at_5")),
            )
        )
    lines.append("")
    return "\n".join(lines)


def _metric_row(name: str, metrics: dict) -> str:
    return (
        f"| {name} | {metrics.get('n')} | {metrics.get('n_pos')} | {_fmt(metrics.get('roc_auc'))} | "
        f"{_fmt(metrics.get('average_precision'))} | {_fmt(metrics.get('precision_at_5'))} | "
        f"{_fmt(metrics.get('precision_at_10'))} | {_fmt(metrics.get('brier'))} |"
    )


def _fmt(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


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
            "train_ranker",
            "evaluate",
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
        "train_ranker": train_ranker,
        "evaluate": evaluate,
        "score_candidates": score_candidates,
        "export_snapshot": export_snapshot,
        "build_all": build_all,
    }
    commands[args.command]()


if __name__ == "__main__":
    main()
