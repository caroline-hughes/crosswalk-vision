from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from .features import attach_labels, borough_from_nta, rows_have_image_metrics
from .heuristic import HeuristicCrosswalkScorer, ScoringInput
from .learned import LearnedPriorityScorer
from .spatial_split import neighborhood_group_kfold, neighborhood_ids


def heuristic_ranking_score(row: Mapping[str, object], *, include_complaints: bool = True) -> float:
    scorer = HeuristicCrosswalkScorer()
    scored = scorer.score(_scoring_input_from_row(row), include_complaints=include_complaints)
    return float(scored.rank_score)


def binary_metrics(y_true: Sequence[int], scores: Sequence[float], ks: tuple[int, ...] = (5, 10)) -> dict:
    y = np.asarray(y_true, dtype=int)
    s = np.asarray(scores, dtype=float)
    n = int(y.size)
    n_pos = int(y.sum()) if n else 0
    result: dict = {
        "n": n,
        "n_pos": n_pos,
        "positive_rate": (n_pos / n) if n else None,
        "roc_auc": None,
        "average_precision": None,
        "brier": None,
    }
    if n == 0:
        result["note"] = "no rows"
        return result
    if n_pos == 0 or n_pos == n:
        result["note"] = "undefined: only one class present"
    else:
        result["roc_auc"] = float(roc_auc_score(y, s))
        result["average_precision"] = float(average_precision_score(y, s))
    order = np.argsort(-s, kind="mergesort")
    for k in ks:
        take = min(int(k), n)
        result[f"precision_at_{k}"] = float(y[order[:take]].mean()) if take else None
    clipped = np.clip(s, 0.0, 1.0)
    result["brier"] = float(np.mean((clipped - y) ** 2))
    return result


def evaluate_spatial_cv(rows: Sequence[Mapping[str, object]]) -> dict:
    definition, include_311, labeled = attach_labels(rows)
    if len(labeled) < 4:
        return {
            "label_definition": definition,
            "include_311_feature": include_311,
            "n": len(labeled),
            "note": "too few rows for spatial CV",
        }

    include_image = rows_have_image_metrics(labeled)
    groups = neighborhood_ids(labeled)
    unique_groups = sorted(set(groups))
    y = np.array([int(row["label"]) for row in labeled], dtype=int)
    heuristic_scores = np.array(
        [heuristic_ranking_score(row, include_complaints=include_311) for row in labeled],
        dtype=float,
    )
    oof = np.full(len(labeled), np.nan, dtype=float)
    per_neighborhood: list[dict] = []

    for train_idx, test_idx in neighborhood_group_kfold(labeled):
        train_rows = [labeled[i] for i in train_idx]
        test_rows = [labeled[i] for i in test_idx]
        scorer = LearnedPriorityScorer(
            include_311=include_311,
            include_image=include_image,
            label_definition=definition,
        )
        scorer.fit(train_rows)
        fold_scores = scorer.predict_scores(test_rows)
        oof[test_idx] = fold_scores
        test_groups = sorted({groups[i] for i in test_idx})
        learned_metrics = binary_metrics(y[test_idx], fold_scores)
        heuristic_metrics = binary_metrics(y[test_idx], heuristic_scores[test_idx])
        learned_metrics.pop("brier", None)
        for neighborhood in test_groups:
            mask = np.array([groups[i] == neighborhood for i in test_idx])
            local_y = y[test_idx][mask]
            local_learned = fold_scores[mask]
            local_heuristic = heuristic_scores[test_idx][mask]
            per_neighborhood.append(
                {
                    "neighborhood_id": neighborhood,
                    "neighborhood_name": _name_for(labeled, neighborhood),
                    "learned": binary_metrics(local_y, local_learned),
                    "heuristic": _ranking_only(binary_metrics(local_y, local_heuristic)),
                }
            )

    finite = np.isfinite(oof)
    overall_learned = binary_metrics(y[finite], oof[finite])
    overall_heuristic = _ranking_only(binary_metrics(y[finite], heuristic_scores[finite]))
    by_neighborhood = _trim_neighborhood_table(per_neighborhood)
    return {
        "label_definition": definition,
        "include_311_feature": include_311,
        "include_image_feature": include_image,
        "n": int(y.size),
        "n_pos": int(y.sum()),
        "neighborhoods": unique_groups,
        "n_neighborhoods": len(unique_groups),
        "split": "GroupKFold by neighborhood_id (train/test NTAs are disjoint)",
        "caveat": (
            "Pedestrian-crash coordinates are noisy and weakly supervised: a nearby crash "
            "does not prove the crossing paint caused it, and many crossings have no crash "
            "because of exposure, not because markings are fine. Metrics are reported only "
            "when both classes are present; otherwise they are null. Citywide ranking is "
            "GIS-only (no per-intersection ortho); this is a learned tabular ranker, not a "
            "vision detector."
        ),
        "overall": {
            "learned": overall_learned,
            "heuristic": overall_heuristic,
        },
        "by_borough": _metrics_by_borough(labeled, y, oof, heuristic_scores, finite),
        "by_neighborhood": by_neighborhood,
        "neighborhood_table_note": (
            "Full NTA list is large citywide; table keeps NTAs with n>=25, up to 12 largest."
        ),
    }


def fit_production_scorer(rows: Sequence[Mapping[str, object]]) -> LearnedPriorityScorer:
    definition, include_311, labeled = attach_labels(rows)
    include_image = rows_have_image_metrics(labeled)
    scorer = LearnedPriorityScorer(
        include_311=include_311,
        include_image=include_image,
        label_definition=definition,
    )
    scorer.fit(labeled)
    return scorer


def _ranking_only(metrics: dict) -> dict:
    metrics = dict(metrics)
    metrics.pop("brier", None)
    metrics["note"] = (
        (metrics.get("note") + "; " if metrics.get("note") else "")
        + "heuristic scores are not probabilities; Brier is omitted"
    ).strip("; ")
    return metrics


def _name_for(rows: Sequence[Mapping[str, object]], neighborhood_id: str) -> str:
    for row in rows:
        if str(row.get("neighborhood_id") or "") == neighborhood_id:
            return str(row.get("neighborhood_name") or neighborhood_id)
    return neighborhood_id


def _trim_neighborhood_table(
    rows: Sequence[Mapping[str, object]],
    *,
    min_n: int = 25,
    limit: int = 12,
) -> list[dict]:
    usable = []
    for row in rows:
        learned = row.get("learned") or {}
        n = int(learned.get("n") or 0)
        if n >= min_n:
            usable.append(dict(row))
    usable.sort(key=lambda item: int((item.get("learned") or {}).get("n") or 0), reverse=True)
    return usable[:limit]


def _metrics_by_borough(
    labeled: Sequence[Mapping[str, object]],
    y: np.ndarray,
    oof: np.ndarray,
    heuristic_scores: np.ndarray,
    finite: np.ndarray,
) -> list[dict]:
    boroughs = np.array(
        [
            borough_from_nta(row.get("neighborhood_id"), row.get("borough"))
            for row in labeled
        ]
    )
    out: list[dict] = []
    for name in ("Manhattan", "Bronx", "Brooklyn", "Queens", "Staten Island"):
        mask = finite & (boroughs == name)
        if not np.any(mask):
            continue
        out.append(
            {
                "borough": name,
                "learned": binary_metrics(y[mask], oof[mask]),
                "heuristic": _ranking_only(binary_metrics(y[mask], heuristic_scores[mask])),
            }
        )
    return out


def _scoring_input_from_row(row: Mapping[str, object]) -> ScoringInput:
    def _float(key: str, default: float = 0.0) -> float:
        value = row.get(key)
        if value is None or value == "":
            return default
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if np.isnan(number):
            return default
        return number

    return ScoringInput(
        id=str(row.get("id") or ""),
        paint_missing_ratio=_float("paint_missing_ratio"),
        stripe_break_ratio=_float("stripe_break_ratio"),
        contrast_score=_float("contrast_score"),
        occlusion_penalty=_float("occlusion_penalty"),
        school_zone=bool(row.get("school_zone")),
        pavement_marking_311_count_since_2020=int(row.get("pavement_marking_311_count_since_2020") or 0),
        image_metrics_missing=bool(row.get("image_metrics_missing")),
    )
