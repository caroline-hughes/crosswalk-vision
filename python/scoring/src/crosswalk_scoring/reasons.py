from __future__ import annotations

from typing import Mapping, Sequence


def build_priority_reason(row: Mapping[str, object]) -> str:
    neighborhood = str(row.get("neighborhood_name") or row.get("neighborhood") or "").strip()
    head = f"Inspect first in {neighborhood}" if neighborhood else "Inspect first"
    parts: list[str] = []

    paint = _optional_float(row.get("paint_missing_ratio"))
    contrast = _optional_float(row.get("contrast_score"))
    stripe = _optional_float(row.get("stripe_break_ratio"))
    crashes = int(row.get("pedestrian_crash_count") or 0)
    complaints = int(row.get("pavement_marking_311_count_since_2020") or 0)
    image_missing = bool(row.get("image_metrics_missing"))

    if not image_missing:
        if paint is not None and paint >= 0.35:
            parts.append("2024 ortho looks under-marked")
        if contrast is not None and contrast <= 0.45:
            parts.append("low marking contrast")
        if stripe is not None and stripe >= 0.35:
            parts.append("broken stripe pattern")
    if crashes:
        noun = "event" if crashes == 1 else "events"
        parts.append(f"{crashes} nearby pedestrian-crash {noun} since 2020")
    if complaints:
        noun = "report" if complaints == 1 else "reports"
        parts.append(f"{complaints} faded-marking 311 {noun} since 2020")
    if row.get("school_zone"):
        parts.append("near an elementary/K-8 school")

    if not parts:
        return f"{head}: geometry and complaint features only."
    return f"{head}: {'; '.join(parts)}."


def build_model_reason(
    row: Mapping[str, object],
    top_features: Sequence[Mapping[str, object]] | None = None,
) -> str:
    """Short, AI-forward line: the ranker (not a detector) flagged this node."""
    neighborhood = str(row.get("neighborhood_name") or row.get("neighborhood") or "").strip()
    loc = f" in {neighborhood}" if neighborhood else ""
    raisers = [
        str(item.get("label") or item.get("feature") or "")
        for item in (top_features or [])
        if float(item.get("contribution") or 0) > 0
    ]
    raisers = [name for name in raisers if name]
    if raisers:
        return f"Why the model flagged this{loc}: {', '.join(raisers)}."
    return build_priority_reason(row)


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
