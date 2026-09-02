from __future__ import annotations

from typing import Mapping


def build_priority_reason(row: Mapping[str, object]) -> str:
    neighborhood = str(row.get("neighborhood_name") or "").strip()
    head = f"Inspect first in {neighborhood}" if neighborhood else "Inspect first"
    parts: list[str] = []

    paint = _optional_float(row.get("paint_missing_ratio"))
    contrast = _optional_float(row.get("contrast_score"))
    stripe = _optional_float(row.get("stripe_break_ratio"))
    crashes = int(row.get("pedestrian_crash_count") or 0)
    complaints = int(row.get("pavement_marking_311_count_since_2020") or 0)

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
        parts.append("school zone")

    if not parts:
        return f"{head}: geometry and imagery features only."
    return f"{head}: {'; '.join(parts)}."


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
