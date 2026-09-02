from __future__ import annotations

from typing import Iterable, Iterator, Mapping, Sequence

import numpy as np
from sklearn.model_selection import GroupKFold


def neighborhood_ids(rows: Sequence[Mapping[str, object]]) -> list[str]:
    ids: list[str] = []
    for row in rows:
        value = str(row.get("neighborhood_id") or row.get("neighborhood") or "").strip()
        if not value:
            value = "UNKNOWN"
        ids.append(value)
    return ids


def assert_disjoint_neighborhoods(
    train_rows: Sequence[Mapping[str, object]],
    test_rows: Sequence[Mapping[str, object]],
) -> None:
    train_groups = set(neighborhood_ids(train_rows))
    test_groups = set(neighborhood_ids(test_rows))
    overlap = train_groups & test_groups
    if overlap:
        raise AssertionError(f"spatial split leaked neighborhoods: {sorted(overlap)}")


def holdout_by_neighborhoods(
    rows: Sequence[Mapping[str, object]],
    test_neighborhoods: Iterable[str],
) -> tuple[list[dict], list[dict]]:
    held_out = {str(name) for name in test_neighborhoods}
    train = [dict(row) for row in rows if str(row.get("neighborhood_id") or "") not in held_out]
    test = [dict(row) for row in rows if str(row.get("neighborhood_id") or "") in held_out]
    assert_disjoint_neighborhoods(train, test)
    return train, test


def neighborhood_group_kfold(
    rows: Sequence[Mapping[str, object]],
    n_splits: int | None = None,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    groups = np.array(neighborhood_ids(rows))
    unique_groups = np.unique(groups)
    if unique_groups.size < 2:
        raise ValueError("spatial CV requires at least two neighborhoods")

    splits = n_splits if n_splits is not None else min(5, int(unique_groups.size))
    splits = max(2, min(splits, int(unique_groups.size)))
    fold = GroupKFold(n_splits=splits)
    indices = np.arange(len(rows))
    labels = np.array([int(row.get("label") or 0) for row in rows])
    for train_idx, test_idx in fold.split(indices, labels, groups):
        train_groups = set(groups[train_idx].tolist())
        test_groups = set(groups[test_idx].tolist())
        if train_groups & test_groups:
            raise AssertionError("GroupKFold leaked neighborhoods")
        yield train_idx, test_idx
