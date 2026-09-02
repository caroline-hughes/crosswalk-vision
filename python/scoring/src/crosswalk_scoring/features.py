from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

IMAGE_FEATURES: tuple[str, ...] = (
    "paint_missing_ratio",
    "stripe_break_ratio",
    "contrast_score",
    "occlusion_penalty",
)
GIS_FEATURES: tuple[str, ...] = (
    "school_zone",
    "street_width_ft",
    "approach_street_count",
    "heading_spread",
)
COMPLAINT_FEATURE = "pavement_marking_311_count_since_2020"

# Crash-only labels may use 311 counts as a predictor. Composite labels must not:
# that would leak the target into the feature matrix.
MIN_CRASH_POSITIVES = 8


def feature_names(*, include_311: bool) -> list[str]:
    names = list(IMAGE_FEATURES + GIS_FEATURES)
    if include_311:
        names.append(COMPLAINT_FEATURE)
    return names


def heading_spread_degrees(row: Mapping[str, object]) -> float:
    primary = _optional_float(row.get("heading_degrees"))
    secondary = _optional_float(row.get("secondary_heading_degrees"))
    if primary is None or secondary is None:
        return 90.0
    diff = abs(primary - secondary) % 180.0
    return float(min(diff, 180.0 - diff))


def row_to_vector(row: Mapping[str, object], *, include_311: bool) -> np.ndarray:
    values: list[float] = []
    for name in IMAGE_FEATURES:
        values.append(_nan_if_missing(row.get(name)))
    values.append(1.0 if bool(row.get("school_zone")) else 0.0)
    values.append(_nan_if_missing(row.get("street_width_ft"), empty_zero=True))
    approach = row.get("approach_street_count")
    values.append(float(approach) if approach not in (None, "") else 2.0)
    values.append(heading_spread_degrees(row))
    if include_311:
        count = row.get("pavement_marking_311_count_since_2020") or 0
        values.append(float(count))
    return np.asarray(values, dtype=float)


def rows_to_matrix(rows: Sequence[Mapping[str, object]], *, include_311: bool) -> np.ndarray:
    if not rows:
        return np.zeros((0, len(feature_names(include_311=include_311))), dtype=float)
    return np.vstack([row_to_vector(row, include_311=include_311) for row in rows])


def choose_label_definition(rows: Sequence[Mapping[str, object]]) -> tuple[str, bool]:
    crash_positives = sum(1 for row in rows if int(row.get("pedestrian_crash_count") or 0) > 0)
    if crash_positives >= MIN_CRASH_POSITIVES:
        return "pedestrian_crash_nearby", True
    return "crash_or_311_faded_marking", False


def attach_labels(rows: Sequence[Mapping[str, object]]) -> tuple[str, bool, list[dict]]:
    definition, include_311 = choose_label_definition(rows)
    labeled: list[dict] = []
    for row in rows:
        item = dict(row)
        crash = int(item.get("pedestrian_crash_count") or 0) > 0
        complaint = int(item.get("pavement_marking_311_count_since_2020") or 0) > 0
        if definition == "pedestrian_crash_nearby":
            item["label"] = int(crash)
        else:
            item["label"] = int(crash or complaint)
        labeled.append(item)
    return definition, include_311, labeled


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


def _nan_if_missing(value: object, *, empty_zero: bool = False) -> float:
    if value is None or value == "":
        return 0.0 if empty_zero else float("nan")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float("nan")
    if empty_zero and number == 0.0:
        return float("nan")
    return number
