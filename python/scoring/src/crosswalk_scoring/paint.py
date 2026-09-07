from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

LABEL_FADED_MARKING = "faded_marking_311_or_looks_bad"

# Image-only fade score. Higher = markings look more degraded in the ortho crop.
PAINT_MISSING_WEIGHT = 0.45
STRIPE_BREAK_WEIGHT = 0.35
LOW_CONTRAST_WEIGHT = 0.20

# Weak-label seed: treat high image-heuristic fade as an extra positive.
LOOKS_BAD_THRESHOLD = 0.48

# Hard visual gate: plot only the top quintile of image fade, and never
# below this floor even if the quintile is soft.
IMAGE_GATE_QUANTILE = 0.80
IMAGE_GATE_FLOOR = 0.42

# Urgency may reorder the paint-bad set. It cannot pass the visual gate.
SCHOOL_URGENCY = 0.10
CRASH_URGENCY = 0.06
MAX_CRASH_FOR_URGENCY = 5


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(number):
        return None
    return number


def _clamp(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def image_metrics_available(row: Mapping[str, object]) -> bool:
    if row.get("image_metrics_missing") is True:
        return False
    return any(
        _optional_float(row.get(name)) is not None
        for name in ("paint_missing_ratio", "stripe_break_ratio", "contrast_score")
    )


def image_paint_score(row: Mapping[str, object]) -> float:
    """0–1 image fade score. Ignores street width, school, 311, and crashes."""
    if not image_metrics_available(row):
        return float("nan")
    paint_missing = _clamp(_optional_float(row.get("paint_missing_ratio")) or 0.0)
    stripe_break = _clamp(_optional_float(row.get("stripe_break_ratio")) or 0.0)
    contrast = _clamp(_optional_float(row.get("contrast_score")) or 0.0)
    return round(
        _clamp(
            PAINT_MISSING_WEIGHT * paint_missing
            + STRIPE_BREAK_WEIGHT * stripe_break
            + LOW_CONTRAST_WEIGHT * (1.0 - contrast)
        ),
        4,
    )


def looks_faded_heuristic(row: Mapping[str, object], *, threshold: float = LOOKS_BAD_THRESHOLD) -> bool:
    score = image_paint_score(row)
    if np.isnan(score):
        return False
    return score >= threshold


def urgency_boost(row: Mapping[str, object]) -> float:
    """Small 0–1 add-on for sort-within-gated-set only."""
    school = SCHOOL_URGENCY if bool(row.get("school_zone")) else 0.0
    crashes = min(int(row.get("pedestrian_crash_count") or 0), MAX_CRASH_FOR_URGENCY)
    crash = CRASH_URGENCY * (crashes / MAX_CRASH_FOR_URGENCY)
    return round(school + crash, 4)


def visual_gate_threshold(scores: Sequence[float], *, quantile: float = IMAGE_GATE_QUANTILE) -> float:
    finite = [float(score) for score in scores if score == score]
    if not finite:
        return IMAGE_GATE_FLOOR
    cutoff = float(np.quantile(np.asarray(finite, dtype=float), quantile))
    return round(max(IMAGE_GATE_FLOOR, cutoff), 4)


def passes_visual_gate(row: Mapping[str, object], *, threshold: float) -> bool:
    score = image_paint_score(row)
    if np.isnan(score):
        return False
    return score >= threshold


def remaking_priority(row: Mapping[str, object], *, model_score: float | None = None) -> float:
    """Display / sort score for the paint-bad set: image fade + learned, then urgency."""
    image = image_paint_score(row)
    if np.isnan(image):
        return float("nan")
    learned = _optional_float(model_score if model_score is not None else row.get("model_score"))
    if learned is None:
        learned = image
    blended = 0.72 * image + 0.28 * _clamp(learned)
    return round(_clamp(blended + urgency_boost(row)), 4)


def attach_paint_labels(rows: Sequence[Mapping[str, object]]) -> tuple[str, bool, list[dict]]:
    """Weak label: nearby 311 faded marking OR high image-heuristic fade.

    311 is the label, not a feature (avoids leaking the target). Crash is never
    the label. School is urgency-only and is not in this label.
    """
    labeled: list[dict] = []
    for row in rows:
        item = dict(row)
        image = image_paint_score(item)
        item["image_paint_score"] = None if np.isnan(image) else float(image)
        complaint = int(item.get("pavement_marking_311_count_since_2020") or 0) > 0
        looks_bad = looks_faded_heuristic(item)
        item["looks_faded_seed"] = bool(looks_bad)
        item["label"] = int(complaint or looks_bad)
        labeled.append(item)
    return LABEL_FADED_MARKING, False, labeled
