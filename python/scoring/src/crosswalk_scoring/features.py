from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

from .paint import attach_paint_labels

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

FEATURE_LABELS: dict[str, str] = {
    "paint_missing_ratio": "ortho paint-missing ratio",
    "stripe_break_ratio": "stripe-break ratio",
    "contrast_score": "marking contrast",
    "occlusion_penalty": "ortho occlusion",
    "school_zone": "near elementary/K-8 school",
    "street_width_ft": "street width",
    "approach_street_count": "number of approach streets",
    "heading_spread": "approach heading spread",
    COMPLAINT_FEATURE: "311 faded-marking complaints",
}

BOROUGH_FROM_NTA_PREFIX: dict[str, str] = {
    "MN": "Manhattan",
    "BX": "Bronx",
    "BK": "Brooklyn",
    "QN": "Queens",
    "SI": "Staten Island",
}

# Kept for older crash-label tests. Production ranking no longer uses it.
MIN_CRASH_POSITIVES = 8


def feature_names(
    *,
    include_311: bool,
    include_image: bool = True,
    include_gis: bool = False,
) -> list[str]:
    names: list[str] = list(IMAGE_FEATURES) if include_image else []
    if include_gis:
        names.extend(GIS_FEATURES)
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


def row_to_vector(
    row: Mapping[str, object],
    *,
    include_311: bool,
    include_image: bool = True,
    include_gis: bool = False,
) -> np.ndarray:
    values: list[float] = []
    if include_image:
        for name in IMAGE_FEATURES:
            values.append(_nan_if_missing(row.get(name)))
    if include_gis:
        values.append(1.0 if bool(row.get("school_zone")) else 0.0)
        values.append(_nan_if_missing(row.get("street_width_ft"), empty_zero=True))
        approach = row.get("approach_street_count")
        values.append(float(approach) if approach not in (None, "") else 2.0)
        values.append(heading_spread_degrees(row))
    if include_311:
        count = row.get("pavement_marking_311_count_since_2020") or 0
        values.append(float(count))
    return np.asarray(values, dtype=float)


def rows_to_matrix(
    rows: Sequence[Mapping[str, object]],
    *,
    include_311: bool,
    include_image: bool = True,
    include_gis: bool = False,
) -> np.ndarray:
    names = feature_names(include_311=include_311, include_image=include_image, include_gis=include_gis)
    if not rows:
        return np.zeros((0, len(names)), dtype=float)
    return np.vstack(
        [
            row_to_vector(
                row,
                include_311=include_311,
                include_image=include_image,
                include_gis=include_gis,
            )
            for row in rows
        ]
    )


def rows_have_image_metrics(rows: Sequence[Mapping[str, object]]) -> bool:
    """True when at least one row has a real ortho-derived feature."""
    for row in rows:
        if row.get("image_metrics_missing") is True:
            continue
        for name in IMAGE_FEATURES:
            if _optional_float(row.get(name)) is not None:
                return True
    return False


def choose_label_definition(rows: Sequence[Mapping[str, object]]) -> tuple[str, bool]:
    """Paint/remaking label. 311 is the weak target, so it is not a feature."""
    _ = rows
    return "faded_marking_311_or_looks_bad", False


def attach_labels(rows: Sequence[Mapping[str, object]]) -> tuple[str, bool, list[dict]]:
    return attach_paint_labels(rows)


def borough_from_nta(nta_id: object, borough: object = "") -> str:
    named = str(borough or "").strip()
    if named:
        return named
    prefix = str(nta_id or "")[:2].upper()
    return BOROUGH_FROM_NTA_PREFIX.get(prefix, "Unknown")


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
