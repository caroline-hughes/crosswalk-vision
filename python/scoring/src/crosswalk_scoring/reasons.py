from __future__ import annotations

from typing import Mapping, Sequence

from .paint import image_paint_score


def build_priority_reason(row: Mapping[str, object]) -> str:
    neighborhood = str(row.get("neighborhood_name") or row.get("neighborhood") or "").strip()
    head = f"Remake first in {neighborhood}" if neighborhood else "Remake first"
    parts: list[str] = []

    paint = _optional_float(row.get("paint_missing_ratio"))
    contrast = _optional_float(row.get("contrast_score"))
    stripe = _optional_float(row.get("stripe_break_ratio"))
    image = image_paint_score(row)
    complaints = int(row.get("pavement_marking_311_count_since_2020") or 0)
    image_missing = bool(row.get("image_metrics_missing"))

    if not image_missing:
        if paint is not None and paint >= 0.35:
            parts.append("2024 ortho looks under-marked")
        if contrast is not None and contrast <= 0.45:
            parts.append("low marking contrast")
        if stripe is not None and stripe >= 0.35:
            parts.append("broken stripe pattern")
        if not parts and image == image and image >= 0.42:
            parts.append("ortho paint metrics look degraded")
    if complaints:
        noun = "report" if complaints == 1 else "reports"
        parts.append(f"{complaints} faded-marking 311 {noun} since 2020 (lane lines mixed with crosswalks)")
    if row.get("school_zone"):
        parts.append("near an elementary/K-8 school (raises urgency)")

    if not parts:
        return f"{head}: image paint metrics and 311 only."
    return f"{head}: {'; '.join(parts)}."


def build_model_reason(
    row: Mapping[str, object],
    top_features: Sequence[Mapping[str, object]] | None = None,
) -> str:
    """Short line: paint/311 ranker (not a detector) flagged this node."""
    neighborhood = str(row.get("neighborhood_name") or row.get("neighborhood") or "").strip()
    loc = f" in {neighborhood}" if neighborhood else ""
    paint_names = {
        "paint_missing_ratio",
        "stripe_break_ratio",
        "contrast_score",
        "occlusion_penalty",
        "pavement_marking_311_count_since_2020",
    }
    raisers = []
    for item in top_features or []:
        if float(item.get("contribution") or 0) <= 0:
            continue
        name = str(item.get("feature") or "")
        label = str(item.get("label") or name)
        if name in paint_names or "paint" in label or "stripe" in label or "contrast" in label or "311" in label:
            raisers.append(label)
        elif label:
            raisers.append(label)
    raisers = [name for name in raisers if name]
    if raisers:
        return f"Why flagged for remaking{loc}: {', '.join(raisers)}."
    return build_priority_reason(row)


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
