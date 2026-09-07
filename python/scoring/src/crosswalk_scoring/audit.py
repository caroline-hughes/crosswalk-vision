from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from .evaluate import evaluate_audit_agreement
from .paint import IMAGE_GATE_FLOOR, image_paint_score, looks_faded_heuristic


AUDIT_TARGET = 160
AUDIT_KS = (10, 20, 50)


def seed_audit_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    target_n: int = AUDIT_TARGET,
    rng_seed: int = 20240906,
) -> list[dict]:
    """Stratified sample with provisional looks_faded seeds from the image heuristic."""
    usable = [dict(row) for row in rows if image_paint_score(row) == image_paint_score(row)]
    if not usable:
        return []
    usable.sort(key=lambda row: str(row.get("id") or ""))
    by_bucket: dict[str, list[dict]] = {}
    for row in usable:
        borough = str(row.get("borough") or "Unknown")
        faded = looks_faded_heuristic(row)
        key = f"{borough}|{'faded' if faded else 'ok'}"
        by_bucket.setdefault(key, []).append(row)

    rng = np.random.default_rng(rng_seed)
    per_bucket = max(4, target_n // max(1, len(by_bucket)))
    picked: list[dict] = []
    picked_ids: set[str] = set()
    for key in sorted(by_bucket):
        bucket = by_bucket[key]
        take = min(len(bucket), per_bucket)
        if take <= 0:
            continue
        indices = rng.choice(len(bucket), size=take, replace=False)
        for idx in indices:
            item = dict(bucket[int(idx)])
            cid = str(item.get("id") or "")
            if cid in picked_ids:
                continue
            item["looks_faded"] = looks_faded_heuristic(item)
            item["audit_provisional"] = True
            item["audit_seed"] = "image_heuristic"
            picked.append(item)
            picked_ids.add(cid)

    if len(picked) < target_n:
        remainder = [row for row in usable if str(row.get("id") or "") not in picked_ids]
        extra = min(len(remainder), target_n - len(picked))
        if extra:
            indices = rng.choice(len(remainder), size=extra, replace=False)
            for idx in indices:
                item = dict(remainder[int(idx)])
                item["looks_faded"] = looks_faded_heuristic(item)
                item["audit_provisional"] = True
                item["audit_seed"] = "image_heuristic"
                picked.append(item)

    picked.sort(key=lambda row: (-float(image_paint_score(row)), str(row.get("id") or "")))
    return picked[:target_n]


def apply_spot_checks(rows: Sequence[Mapping[str, object]]) -> list[dict]:
    """Override a few well-known failure / faded modes after visual review."""
    # Victory Blvd & Richmond Avenue: intact continental bars; must not be faded.
    overrides: dict[str, bool] = {
        "nyc-3900": False,
        "nyc-5992": False,
    }
    updated: list[dict] = []
    for row in rows:
        item = dict(row)
        cid = str(item.get("id") or "")
        if cid in overrides:
            item["looks_faded"] = overrides[cid]
            item["audit_seed"] = "spot_check"
        updated.append(item)
    return updated


def write_audit_exports(rows: Sequence[Mapping[str, object]], directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    seeded = apply_spot_checks(rows)
    payload = {
        row["id"]: {
            "looks_faded": bool(row.get("looks_faded")),
            "provisional": True,
            "seed": str(row.get("audit_seed") or "image_heuristic"),
            "image_paint_score": _finite(image_paint_score(row)),
            "intersection_label": str(row.get("intersection_label") or ""),
            "borough": str(row.get("borough") or ""),
            "neighborhood_id": str(row.get("neighborhood_id") or ""),
        }
        for row in seeded
        if row.get("id")
    }
    json_path = directory / "audit_labels.json"
    csv_path = directory / "audit_labels.csv"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "looks_faded",
                "provisional",
                "seed",
                "image_paint_score",
                "intersection_label",
                "borough",
                "neighborhood_id",
                "notes",
            ],
        )
        writer.writeheader()
        for cid, item in payload.items():
            writer.writerow(
                {
                    "id": cid,
                    "looks_faded": item["looks_faded"],
                    "provisional": True,
                    "seed": item["seed"],
                    "image_paint_score": item["image_paint_score"],
                    "intersection_label": item["intersection_label"],
                    "borough": item["borough"],
                    "neighborhood_id": item["neighborhood_id"],
                    "notes": "",
                }
            )
    report = evaluate_audit_agreement(seeded, ks=AUDIT_KS)
    report["gate_floor"] = IMAGE_GATE_FLOOR
    report["n_seeded"] = len(payload)
    (directory / "audit_eval.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (directory / "audit_eval.md").write_text(_audit_markdown(report), encoding="utf-8")
    return report


def _finite(value: float) -> float | None:
    if value != value:
        return None
    return float(value)


def _audit_markdown(report: dict) -> str:
    metrics = report.get("metrics") or {}
    lines = [
        "# Paint audit (provisional)",
        "",
        report.get("note") or "",
        "",
        f"- n = {report.get('n')} (positives = {report.get('n_pos')})",
        f"- NTAs represented: {report.get('n_neighborhoods')}",
        f"- Visual-gate floor: {report.get('gate_floor')}",
        "",
        "| k | precision@k vs looks_faded |",
        "| --- | --- |",
    ]
    for key, value in metrics.items():
        if key.startswith("precision_at_"):
            k = key.replace("precision_at_", "")
            pretty = f"{value:.3f}" if isinstance(value, float) else "n/a"
            lines.append(f"| {k} | {pretty} |")
    if metrics.get("roc_auc") is not None:
        lines.extend(["", f"- ROC-AUC vs looks_faded: {metrics['roc_auc']:.3f}"])
    lines.append("")
    return "\n".join(lines)
