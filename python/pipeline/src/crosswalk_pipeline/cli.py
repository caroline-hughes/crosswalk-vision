from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from crosswalk_scoring import (
    DEFAULT_MODEL_PATH,
    IMAGE_GATE_FLOOR,
    IMAGE_GATE_QUANTILE,
    LABEL_FADED_MARKING,
    HeuristicCrosswalkScorer,
    LearnedPriorityScorer,
    ScoringInput,
    attach_labels,
    borough_from_nta,
    build_model_reason,
    evaluate_spatial_cv,
    fit_production_scorer,
    image_paint_score,
    remaking_priority,
    seed_audit_rows,
    urgency_boost,
    visual_gate_threshold,
    write_audit_exports,
)

from .artifact_store import LocalArtifactStore
from .config import ORTHO_LABEL, ORTHO_PREFERRED_NEXT_YEAR, ORTHO_UPGRADE_NOTE, ORTHO_YEAR, PATHS
from .io_utils import read_json, write_json
from .live_imagery import analyze_existing_crops, fetch_plottable_imagery
from .live_sources import (
    NYC_LABEL,
    PLOT_MAX,
    PLOT_PERCENTILE,
    RECENT_311_CAP,
    LiveSourceVersions,
    annotate_311_details,
    annotate_crashes,
    annotate_neighborhoods,
    annotate_school_zones,
    build_live_candidates,
    ensure_live_sources,
    select_plottable,
)
from .models import CandidateRecord, ExportRecord, candidate_from_dict


def fetch_sources() -> None:
    versions = ensure_live_sources()
    manifest = {
        "generated_at": _utc_now(),
        "geography": NYC_LABEL,
        "pilot_boundary": NYC_LABEL,
        "sources": {
            "imagery": {
                "name": "Spring 2024 NYS Orthoimagery (plotted in-need set only)",
                "url": "https://orthos.its.ny.gov/arcgis/rest/services/wms/2024/MapServer",
                "note": (
                    "Reuse 2024 ortho crops on the imagery-backed set (~2k plotted "
                    "nodes) for paint metrics. Remaking priority comes from those "
                    "crops plus 311, then a hard visual gate. Not a detector."
                ),
            },
            "lion": {
                "name": "NYC LION Street Base Map (intersection nodes, five boroughs)",
                "url": "https://data.cityofnewyork.us/City-Government/LION/2v4z-66xt",
            },
            "service_requests_311": {
                "name": "NYC 311 faded/after-repaving line markings (lane lines and crosswalks mixed)",
                "url": "https://data.cityofnewyork.us/resource/erm2-nwe9.json",
                "note": "Socrata default page is 100; fetch paginates with $limit/$offset/$order. Citywide.",
            },
            "school_zones": {
                "name": "DOE school points (elementary / K-8) within 800 ft of the node",
                "url": "https://data.cityofnewyork.us/resource/wg9x-4ke6.json",
            },
            "vision_zero_crashes": {
                "name": "NYPD Motor Vehicle Collisions — pedestrian injured or killed",
                "url": "https://data.cityofnewyork.us/resource/h9gi-nx95.json",
                "filter": "citywide NYC bbox; crash_date >= 2020-01-01; pedestrians injured or killed > 0",
            },
            "neighborhoods": {
                "name": "NYC 2020 Neighborhood Tabulation Areas (all boroughs)",
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
            "LION gdb is not required for tests. Scoring is a sklearn logistic paint/"
            "remaking ranker on ortho metrics (311 is the weak label, not a crash label). "
            "The pixel heuristic is the baseline, not a detector. 311 Line/Marking mixes "
            "lane lines with crosswalks. The map plots only crossings that pass a hard "
            "image-paint visual gate."
        ),
    }
    write_json(PATHS.raw_dir / "source_manifest.json", manifest)


def prepare_candidates() -> None:
    ensure_live_sources()
    candidates = build_live_candidates()
    write_json(
        PATHS.processed_dir / "candidates.json",
        [candidate.to_dict() for candidate in candidates],
        indent=None,
    )


def enrich_candidates() -> None:
    ensure_live_sources()
    candidates = [candidate_from_dict(item) for item in read_json(PATHS.processed_dir / "candidates.json")]
    school_zone_lookup = annotate_school_zones(candidates)
    complaint_detail_lookup = annotate_311_details(candidates)
    crash_lookup = annotate_crashes(candidates)
    neighborhood_lookup = annotate_neighborhoods(candidates)
    # Citywide: do not fetch 2024 ortho crops. GIS features only.
    enriched = []
    for candidate in candidates:
        neighborhood = neighborhood_lookup.get(
            candidate.id,
            {"neighborhood_id": "UNKNOWN", "neighborhood_name": "Unknown", "borough": "Unknown"},
        )
        borough = str(
            neighborhood.get("borough")
            or borough_from_nta(neighborhood.get("neighborhood_id"))
        )
        enriched.append(
            {
                **candidate.to_dict(),
                "school_zone": school_zone_lookup.get(candidate.id, False),
                "pavement_marking_311_count_since_2020": len(complaint_detail_lookup.get(candidate.id, [])),
                "matched_311_complaints": complaint_detail_lookup.get(candidate.id, [])[:RECENT_311_CAP],
                "pedestrian_crash_count": crash_lookup.get(candidate.id, 0),
                "neighborhood_id": neighborhood["neighborhood_id"],
                "neighborhood_name": neighborhood["neighborhood_name"],
                "borough": borough,
                "google_maps_url": f"https://www.google.com/maps?q={candidate.lat},{candidate.lon}",
                "image_metrics_missing": True,
                "paint_missing_ratio": None,
                "stripe_break_ratio": None,
                "contrast_score": None,
                "occlusion_penalty": None,
                "processed_image_path": None,
                "processed_thumbnail_path": None,
            }
        )
    write_json(PATHS.processed_dir / "enriched_candidates.json", enriched, indent=None)


def analyze_imagery() -> None:
    """Attach live_imagery paint metrics to the imagery-backed snapshot rows."""
    rows = _imagery_universe()
    metrics = analyze_existing_crops(rows)
    attached = _attach_metrics(rows, metrics)
    write_json(PATHS.processed_dir / "paint_training_rows.json", attached, indent=None)
    write_json(
        PATHS.processed_dir / "image_metrics.json",
        {
            cid: {
                "paint_missing_ratio": item.paint_missing_ratio,
                "stripe_break_ratio": item.stripe_break_ratio,
                "contrast_score": item.contrast_score,
                "occlusion_penalty": item.occlusion_penalty,
                "image_path": item.image_path,
            }
            for cid, item in metrics.items()
        },
        indent=None,
    )


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
            "include_image_feature": scorer.include_image,
            "include_gis_feature": scorer.include_gis,
            "n": len(labeled),
            "n_pos": sum(int(row["label"]) for row in labeled),
            "feature_names": scorer.feature_names_,
            "geography": NYC_LABEL,
            "neighborhoods": sorted({str(row.get("neighborhood_id") or "") for row in labeled}),
            "artifact": str(PATHS.model_artifact_path),
            "note": (
                "Paint/remaking ranker on ortho metrics. Weak label is 311 faded "
                "marking OR high image-heuristic fade. Crash is not the label. "
                "Street width is not a ranking feature."
            ),
        },
    )


def evaluate() -> None:
    rows = _labeled_training_rows()
    report = evaluate_spatial_cv(rows)
    report["generated_at"] = _utc_now()
    report["geography"] = NYC_LABEL
    definition, _, labeled = attach_labels(rows)
    audit_rows = seed_audit_rows(labeled)
    audit = write_audit_exports(audit_rows, PATHS.export_dir)
    report["audit"] = audit
    write_json(PATHS.eval_json_path, report)
    PATHS.eval_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    PATHS.eval_markdown_path.write_text(_eval_markdown(report), encoding="utf-8")
    store = LocalArtifactStore()
    store.write_export("eval_by_neighborhood.json", json.dumps(report, indent=2).encode("utf-8"))
    store.write_export("eval_by_neighborhood.md", _eval_markdown(report).encode("utf-8"))
    store.write_export("audit_labels.json", (PATHS.export_dir / "audit_labels.json").read_bytes())
    store.write_export("audit_labels.csv", (PATHS.export_dir / "audit_labels.csv").read_bytes())
    store.write_export("audit_eval.json", (PATHS.export_dir / "audit_eval.json").read_bytes())
    store.write_export("audit_eval.md", (PATHS.export_dir / "audit_eval.md").read_bytes())
    _ = definition


def score_candidates() -> None:
    heuristic = HeuristicCrosswalkScorer(confidence_floor=0.0)
    enriched = _labeled_training_rows()
    learned = _load_or_train_scorer(enriched)
    include_complaints = True
    _, _, labeled = attach_labels(enriched)
    model_scores = learned.predict_scores(labeled)
    explanations = learned.explain_rows(labeled, top_k=3)
    scored_records: List[dict] = []

    for item, labeled_row, model_score, top_features in zip(
        enriched, labeled, model_scores, explanations
    ):
        candidate = candidate_from_dict({**item, **{k: labeled_row.get(k, item.get(k)) for k in item}})
        image_missing = bool(item.get("image_metrics_missing", True))
        heuristic_result = heuristic.score(
            ScoringInput(
                id=candidate.id,
                paint_missing_ratio=candidate.paint_missing_ratio,
                stripe_break_ratio=candidate.stripe_break_ratio,
                contrast_score=candidate.contrast_score,
                occlusion_penalty=candidate.occlusion_penalty,
                school_zone=candidate.school_zone,
                pavement_marking_311_count_since_2020=candidate.pavement_marking_311_count_since_2020,
                image_metrics_missing=image_missing,
            ),
            include_complaints=include_complaints,
        )
        score_value = float(model_score)
        if not (score_value == score_value) or score_value in (float("inf"), float("-inf")):
            continue
        merged = {**item, **labeled_row}
        paint = image_paint_score(merged)
        merged["image_paint_score"] = None if paint != paint else float(paint)
        merged["model_score"] = score_value
        display = remaking_priority(merged, model_score=score_value)
        if display != display:
            continue
        reason_tags = [tag for tag in heuristic_result.reason_tags if tag != "school zone"]
        if heuristic_result.reason_tags and "partial paint loss" in heuristic_result.reason_tags:
            pass
        crash_count = int(item.get("pedestrian_crash_count") or 0)
        if crash_count > 0:
            noun = "event" if crash_count == 1 else "events"
            reason_tags.append(f"crash badge: {crash_count} ped. {noun}")
        if candidate.school_zone:
            reason_tags.append("school urgency")
        neighborhood_name = str(item.get("neighborhood_name") or item.get("neighborhood") or "")
        borough = str(item.get("borough") or borough_from_nta(item.get("neighborhood_id")))
        if neighborhood_name:
            reason_tags.append(neighborhood_name)
        scored_records.append(
            {
                **item,
                **merged,
                "label": labeled_row.get("label"),
                "borough": borough,
                "model_score": round(float(display), 4),
                "learned_score": round(score_value, 4),
                "heuristic_score": float(heuristic_result.rank_score),
                "severity_score": int(round(float(display) * 100)),
                "confidence_score": heuristic_result.confidence_score,
                "rank_score": round(float(display), 4),
                "image_paint_score": None if paint != paint else round(float(paint), 4),
                "urgency_score": urgency_boost(merged),
                "reason_tags": reason_tags,
                "top_features": top_features,
                "priority_reason": build_model_reason(merged, top_features),
            }
        )

    scored_records.sort(
        key=lambda record: (
            record["rank_score"],
            record.get("image_paint_score") or 0.0,
            record.get("pavement_marking_311_count_since_2020") or 0,
        ),
        reverse=True,
    )
    write_json(PATHS.processed_dir / "scored_candidates.json", scored_records, indent=None)


def export_snapshot() -> None:
    scored_records = read_json(PATHS.processed_dir / "scored_candidates.json")
    store = LocalArtifactStore()
    export_records: List[ExportRecord] = []
    eval_report = {}
    if PATHS.eval_json_path.exists():
        eval_report = read_json(PATHS.eval_json_path)

    plottable = select_plottable(scored_records)
    imagery = fetch_plottable_imagery(plottable)
    for item in plottable:
        candidate = candidate_from_dict(item)
        image_url, thumbnail_url = _publish_imagery(store, candidate.id, imagery.get(candidate.id), item)
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
                matched_311_complaints=list(item.get("matched_311_complaints") or [])[:RECENT_311_CAP],
                image_url=image_url,
                thumbnail_url=thumbnail_url,
                google_maps_url=item["google_maps_url"],
                model_score=float(item["model_score"]),
                heuristic_score=float(item["heuristic_score"]),
                neighborhood=str(item.get("neighborhood_name") or item.get("neighborhood") or ""),
                neighborhood_id=str(item.get("neighborhood_id") or ""),
                borough=str(item.get("borough") or borough_from_nta(item.get("neighborhood_id"))),
                priority_reason=str(item.get("priority_reason") or ""),
                pedestrian_crash_count=int(item.get("pedestrian_crash_count") or 0),
                top_features=list(item.get("top_features") or []),
                paint_missing_ratio=_optional_metric(item.get("paint_missing_ratio")),
                stripe_break_ratio=_optional_metric(item.get("stripe_break_ratio")),
                contrast_score=_optional_metric(item.get("contrast_score")),
                occlusion_penalty=_optional_metric(item.get("occlusion_penalty")),
                image_paint_score=_optional_metric(item.get("image_paint_score")),
                urgency_score=float(item.get("urgency_score") or 0.0),
                passed_visual_gate=True,
            )
        )

    overall = (eval_report.get("overall") or {}) if isinstance(eval_report, dict) else {}
    learned_auc = (overall.get("learned") or {}).get("roc_auc")
    heuristic_auc = (overall.get("heuristic") or {}).get("roc_auc")
    learned_p5 = (overall.get("learned") or {}).get("precision_at_5")
    learned_p20 = (overall.get("learned") or {}).get("precision_at_20")
    learned_ap = (overall.get("learned") or {}).get("average_precision")
    audit = eval_report.get("audit") or {}
    audit_metrics = audit.get("metrics") or {}
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
    n_scored = len(scored_records)
    n_plotted = len(crosswalk_payload)
    n_with_imagery = sum(1 for row in crosswalk_payload if row.get("image_url") or row.get("thumbnail_url"))
    source_versions["imagery"] = (
        f"{ORTHO_LABEL} (wms/{ORTHO_YEAR}) for {n_with_imagery}/{n_plotted} "
        f"plotted in-need nodes. {ORTHO_UPGRADE_NOTE}"
    )
    gate_values = [row.get("image_paint_score") for row in crosswalk_payload if row.get("image_paint_score") is not None]
    threshold = min((float(v) for v in gate_values), default=None) if gate_values else None
    geojson_payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": row["id"],
                "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
                "properties": {
                    "id": row["id"],
                    "intersection_label": row["intersection_label"],
                    "borough": row["borough"],
                    "neighborhood": row["neighborhood"],
                    "neighborhood_id": row["neighborhood_id"],
                    "model_score": row["model_score"],
                    "heuristic_score": row["heuristic_score"],
                    "severity_score": row["severity_score"],
                    "school_zone": row["school_zone"],
                    "pavement_marking_311_count_since_2020": row["pavement_marking_311_count_since_2020"],
                    "pedestrian_crash_count": row["pedestrian_crash_count"],
                    "image_paint_score": row.get("image_paint_score"),
                    "paint_missing_ratio": row.get("paint_missing_ratio"),
                    "stripe_break_ratio": row.get("stripe_break_ratio"),
                    "contrast_score": row.get("contrast_score"),
                    "priority_reason": row["priority_reason"],
                    "top_features": row["top_features"],
                    "matched_311_complaints": row["matched_311_complaints"],
                    "google_maps_url": row["google_maps_url"],
                    "image_url": row.get("image_url") or "",
                    "thumbnail_url": row.get("thumbnail_url") or "",
                },
            }
            for row in crosswalk_payload
        ],
    }
    meta_payload = {
        "build_timestamp": _utc_now(),
        "source_versions": source_versions,
        "pilot_boundary": NYC_LABEL,
        "geography": NYC_LABEL,
        "total_records": n_plotted,
        "n_scored": n_scored,
        "n_plotted": n_plotted,
        "plot_percentile": PLOT_PERCENTILE,
        "plot_max": PLOT_MAX,
        "plot_threshold": threshold,
        "plot_rule": (
            f"Hard visual gate: plot only crossings whose image paint score is in the top "
            f"{100 - IMAGE_GATE_QUANTILE * 100:.0f}% of the imagery-backed set and at least "
            f"{IMAGE_GATE_FLOOR:.2f}. School and crash boost urgency inside that set only. "
            f"Cap {PLOT_MAX}, with a per-borough floor among gated rows."
        ),
        "visual_gate_quantile": IMAGE_GATE_QUANTILE,
        "visual_gate_floor": IMAGE_GATE_FLOOR,
        "visual_gate_threshold": threshold,
        "scoring_method": (
            "sklearn logistic remaking ranker on ortho paint metrics (paint_missing_ratio, "
            "stripe_break_ratio, contrast_score, occlusion_penalty). Weak label is nearby "
            "311 faded/after-repaving OR high image-heuristic fade. Street width and crash "
            "counts cannot put a good-looking crop in the severe set. Not a vision detector."
        ),
        "label_definition": eval_report.get("label_definition", LABEL_FADED_MARKING),
        "eval_split": eval_report.get("split", "GroupKFold by neighborhood"),
        "eval_n": eval_report.get("n"),
        "eval_n_pos": eval_report.get("n_pos"),
        "eval_learned_auc": learned_auc,
        "eval_heuristic_auc": heuristic_auc,
        "eval_learned_ap": learned_ap,
        "eval_learned_precision_at_5": learned_p5,
        "eval_learned_precision_at_20": learned_p20,
        "eval_audit_n": audit.get("n"),
        "eval_audit_n_pos": audit.get("n_pos"),
        "eval_audit_precision_at_10": audit_metrics.get("precision_at_10"),
        "eval_audit_precision_at_20": audit_metrics.get("precision_at_20"),
        "eval_audit_precision_at_50": audit_metrics.get("precision_at_50"),
        "eval_audit_provisional": True,
        "eval_by_borough": eval_report.get("by_borough") or [],
        "include_image_feature": eval_report.get("include_image_feature", True),
        "include_311_feature": eval_report.get("include_311_feature", False),
        "showcase_top_k": n_plotted,
        **_imagery_meta(n_with_imagery, n_plotted, n_scored),
        "product_claim": (
            "DOT repaint/remaking queue: pedestrian crossings whose markings look "
            "degraded in 2024 aerial imagery, corroborated by 311 faded-marking "
            "complaints. School proximity raises urgency inside the paint-bad set. "
            "Pedestrian crashes are a secondary badge, not the ranking objective."
        ),
        "caveat": (
            "Not a crosswalk detector. Candidates are LION intersection nodes, not painted "
            "polygons. Remaking priority is scored on the imagery-backed set "
            f"({n_scored} crossings with 2024 ortho crops). The map plots {n_plotted} "
            "nodes that pass a hard visual gate on image paint severity — a wide or "
            "crashy crossing with good paint metrics is excluded. 311 Line/Marking "
            "complaints mix lane lines with crosswalks. Audit looks_faded labels are "
            "provisional (heuristic-seeded plus spot checks). Spatial NTA split; treat "
            "AUC as directional, not a production SLA."
        ),
    }

    store.write_export("crosswalks.json", json.dumps(crosswalk_payload).encode("utf-8"))
    store.write_export("crossings.geojson", json.dumps(geojson_payload, separators=(",", ":")).encode("utf-8"))
    store.write_export("meta.json", json.dumps(meta_payload, indent=2).encode("utf-8"))


def fetch_plot_imagery() -> None:
    """Attach 2024 ortho crops to an existing plotted snapshot without rescoring."""
    records_path = PATHS.export_dir / "crosswalks.json"
    if not records_path.exists():
        raise FileNotFoundError("data/export/crosswalks.json is missing; run export_snapshot first.")
    records = read_json(records_path)
    store = LocalArtifactStore()
    imagery = fetch_plottable_imagery(records)
    for item in records:
        image_url, thumbnail_url = _publish_imagery(store, str(item["id"]), imagery.get(str(item["id"])), item)
        item["image_url"] = image_url
        item["thumbnail_url"] = thumbnail_url
    n_with_imagery = sum(1 for row in records if row.get("image_url") or row.get("thumbnail_url"))
    meta_path = PATHS.export_dir / "meta.json"
    meta = read_json(meta_path) if meta_path.exists() else {}
    n_plotted = len(records)
    n_scored = int(meta.get("n_scored") or n_plotted)
    meta.update(_imagery_meta(n_with_imagery, n_plotted, n_scored))
    versions = dict(meta.get("source_versions") or {})
    versions["imagery"] = (
        f"{ORTHO_LABEL} (wms/{ORTHO_YEAR}) for {n_with_imagery}/{n_plotted} "
        f"plotted in-need nodes. {ORTHO_UPGRADE_NOTE}"
    )
    meta["source_versions"] = versions
    if "caveat" in meta:
        meta["caveat"] = (
            "Not a crosswalk detector. Candidates are LION intersection nodes, not painted "
            "polygons. Remaking priority is scored on the imagery-backed set "
            f"({n_scored} crossings with 2024 ortho crops). The map plots {n_plotted} "
            "nodes that pass a hard visual gate on image paint severity. 311 Line/Marking "
            "complaints mix lane lines with crosswalks. Audit labels are provisional."
        )
    geojson_path = PATHS.export_dir / "crossings.geojson"
    if geojson_path.exists():
        geojson = read_json(geojson_path)
        by_id = {row["id"]: row for row in records}
        for feature in geojson.get("features") or []:
            props = feature.get("properties") or {}
            row = by_id.get(str(feature.get("id") or props.get("id") or ""))
            if not row:
                continue
            props["image_url"] = row.get("image_url") or ""
            props["thumbnail_url"] = row.get("thumbnail_url") or ""
            feature["properties"] = props
        store.write_export("crossings.geojson", json.dumps(geojson, separators=(",", ":")).encode("utf-8"))
    store.write_export("crosswalks.json", json.dumps(records).encode("utf-8"))
    store.write_export("meta.json", json.dumps(meta, indent=2).encode("utf-8"))


def rescore_from_imagery() -> None:
    """Re-aim the existing imagery-backed snapshot as a paint/remaking queue."""
    analyze_imagery()
    train_ranker()
    evaluate()
    score_candidates()
    export_snapshot()


def build_all() -> None:
    if (PATHS.export_dir / "crosswalks.json").exists() and PATHS.web_images_dir.exists():
        rescore_from_imagery()
        return
    fetch_sources()
    prepare_candidates()
    enrich_candidates()
    analyze_imagery()
    train_ranker()
    evaluate()
    score_candidates()
    export_snapshot()


def _publish_imagery(store: LocalArtifactStore, candidate_id: str, metrics, item: dict) -> tuple[str, str]:
    if metrics is not None:
        full = Path(metrics.image_path)
        thumb = Path(metrics.thumbnail_path)
        image_url = store.write_crop(candidate_id, full.read_bytes(), ext=full.suffix.lstrip(".") or "jpg") if full.exists() else ""
        thumbnail_url = (
            store.write_thumbnail(candidate_id, thumb.read_bytes(), ext=thumb.suffix.lstrip(".") or "jpg")
            if thumb.exists()
            else ""
        )
        return image_url, thumbnail_url

    processed = item.get("processed_image_path")
    if processed and Path(str(processed)).exists():
        crop_path = Path(str(processed))
        image_url = store.write_crop(candidate_id, crop_path.read_bytes(), ext=crop_path.suffix.lstrip(".") or "png")
        thumb_path = item.get("processed_thumbnail_path")
        thumbnail_url = ""
        if thumb_path and Path(str(thumb_path)).exists():
            thumb = Path(str(thumb_path))
            thumbnail_url = store.write_thumbnail(
                candidate_id, thumb.read_bytes(), ext=thumb.suffix.lstrip(".") or "png"
            )
        return image_url, thumbnail_url
    return str(item.get("image_url") or ""), str(item.get("thumbnail_url") or "")


def _labeled_training_rows() -> list[dict]:
    paint_path = PATHS.processed_dir / "paint_training_rows.json"
    if paint_path.exists():
        rows = read_json(paint_path)
        if rows:
            return rows
    snapshot = PATHS.export_dir / "crosswalks.json"
    if snapshot.exists():
        rows = _attach_metrics(read_json(snapshot), analyze_existing_crops(read_json(snapshot)))
        if rows:
            return rows
    enriched_path = PATHS.processed_dir / "enriched_candidates.json"
    if enriched_path.exists():
        rows = read_json(enriched_path)
        if rows:
            return rows
    for name in ("citywide_training_rows.json", "training_rows.json"):
        fixture_path = PATHS.fixtures_dir / name
        if fixture_path.exists():
            return read_json(fixture_path)
    return []


def _imagery_universe() -> list[dict]:
    for path in (
        PATHS.processed_dir / "paint_training_rows.json",
        PATHS.export_dir / "crosswalks.json",
        PATHS.processed_dir / "scored_candidates.json",
        PATHS.processed_dir / "enriched_candidates.json",
    ):
        if path.exists():
            rows = read_json(path)
            if rows:
                return rows
    return []


def _attach_metrics(rows: list[dict], metrics) -> list[dict]:
    attached: list[dict] = []
    for row in rows:
        item = dict(row)
        if not item.get("neighborhood_name") and item.get("neighborhood"):
            item["neighborhood_name"] = item.get("neighborhood")
        found = metrics.get(str(item.get("id") or ""))
        if found is None:
            item.setdefault("image_metrics_missing", True)
            attached.append(item)
            continue
        item["image_metrics_missing"] = False
        item["paint_missing_ratio"] = found.paint_missing_ratio
        item["stripe_break_ratio"] = found.stripe_break_ratio
        item["contrast_score"] = found.contrast_score
        item["occlusion_penalty"] = found.occlusion_penalty
        item["image_paint_score"] = image_paint_score(item)
        if found.image_path:
            item["processed_image_path"] = found.image_path
        if found.thumbnail_path:
            item["processed_thumbnail_path"] = found.thumbnail_path
        attached.append(item)
    return attached


def _optional_metric(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


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
        f"- Geography: {report.get('geography', NYC_LABEL)}",
        f"- Label: `{report.get('label_definition')}`",
        f"- Split: {report.get('split')}",
        f"- n = {report.get('n')}, positives = {report.get('n_pos')}",
        f"- NTAs in split: {report.get('n_neighborhoods', len(report.get('neighborhoods') or []))}",
        f"- 311 used as a feature: {report.get('include_311_feature')}",
        f"- Image/ortho features: {report.get('include_image_feature')}",
        f"- GIS width/heading features: {report.get('include_gis_feature')}",
        "",
        report.get("caveat") or "",
        "",
        "## Overall (out-of-fold)",
        "",
        "| scorer | n | positives | ROC-AUC | average precision | precision@5 | precision@10 | Brier |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        _metric_row("learned", learned),
        _metric_row("heuristic baseline", heuristic),
        _metric_row("image paint score", overall.get("image_paint") or {}),
        "",
        "## By borough (out-of-fold rows in that borough)",
        "",
        "| borough | n | positives | learned AUC | heuristic AUC | learned P@5 | heuristic P@5 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report.get("by_borough") or []:
        learned_n = row.get("learned") or {}
        heuristic_n = row.get("heuristic") or {}
        lines.append(
            "| {name} | {n} | {pos} | {lauc} | {hauc} | {lp5} | {hp5} |".format(
                name=row.get("borough"),
                n=learned_n.get("n"),
                pos=learned_n.get("n_pos"),
                lauc=_fmt(learned_n.get("roc_auc")),
                hauc=_fmt(heuristic_n.get("roc_auc")),
                lp5=_fmt(learned_n.get("precision_at_5")),
                hp5=_fmt(heuristic_n.get("precision_at_5")),
            )
        )
    lines.extend(
        [
            "",
            "## Sample of NTAs (largest with n≥25; full citywide table omitted)",
            "",
            report.get("neighborhood_table_note") or "",
            "",
            "| NTA | name | n | positives | learned AUC | heuristic AUC | learned P@5 | heuristic P@5 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
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
    audit = report.get("audit") or {}
    if audit:
        metrics = audit.get("metrics") or {}
        lines.extend(
            [
                "",
                "## Audit vs looks_faded (provisional)",
                "",
                audit.get("note") or "",
                "",
                f"- n = {audit.get('n')}, looks_faded positives = {audit.get('n_pos')}",
                f"- precision@10 = {_fmt(metrics.get('precision_at_10'))}",
                f"- precision@20 = {_fmt(metrics.get('precision_at_20'))}",
                f"- precision@50 = {_fmt(metrics.get('precision_at_50'))}",
                "",
            ]
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


def _imagery_meta(n_with_imagery: int, n_plotted: int, n_scored: int) -> dict:
    return {
        "n_with_imagery": n_with_imagery,
        "imagery_year": ORTHO_YEAR,
        "imagery_label": ORTHO_LABEL,
        "imagery_next_year": ORTHO_PREFERRED_NEXT_YEAR,
        "imagery_upgrade_note": ORTHO_UPGRADE_NOTE,
        "imagery_rule": (
            f"{ORTHO_LABEL} (orthos.its.ny.gov wms/{ORTHO_YEAR}) for the plotted in-need "
            f"set ({n_with_imagery}/{n_plotted} plotted nodes have a crop). Paint metrics "
            f"are computed from those crops for the {n_scored} imagery-backed scored nodes. "
            "NYS flew the five boroughs in Spring 2024. 2025 MapServer is Hudson Valley / "
            f"Westchester / etc and is blank over NYC. {ORTHO_UPGRADE_NOTE}"
        ),
    }


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
            "train_ranker",
            "evaluate",
            "score_candidates",
            "export_snapshot",
            "fetch_plot_imagery",
            "analyze_imagery",
            "rescore_from_imagery",
            "build_all",
        ],
    )
    args = parser.parse_args()

    commands = {
        "fetch_sources": fetch_sources,
        "prepare_candidates": prepare_candidates,
        "enrich_candidates": enrich_candidates,
        "analyze_imagery": analyze_imagery,
        "train_ranker": train_ranker,
        "evaluate": evaluate,
        "score_candidates": score_candidates,
        "export_snapshot": export_snapshot,
        "fetch_plot_imagery": fetch_plot_imagery,
        "rescore_from_imagery": rescore_from_imagery,
        "build_all": build_all,
    }
    commands[args.command]()


if __name__ == "__main__":
    main()
