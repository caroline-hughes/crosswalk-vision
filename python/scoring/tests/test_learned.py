import json
import math
import unittest
from pathlib import Path

import numpy as np

from crosswalk_scoring import (
    LearnedPriorityScorer,
    attach_labels,
    assert_disjoint_neighborhoods,
    holdout_by_neighborhoods,
    neighborhood_group_kfold,
    row_to_vector,
)

FIXTURE = Path(__file__).parent / "fixtures" / "training_rows.json"


def _rows() -> list[dict]:
    return json.loads(FIXTURE.read_text())


class SpatialSplitTest(unittest.TestCase):
    def test_holdout_neighborhoods_are_disjoint(self) -> None:
        rows = _rows()
        train, test = holdout_by_neighborhoods(rows, ["MN0301"])
        assert_disjoint_neighborhoods(train, test)
        self.assertTrue(train)
        self.assertTrue(test)
        self.assertTrue(all(row["neighborhood_id"] != "MN0301" for row in train))
        self.assertTrue(all(row["neighborhood_id"] == "MN0301" for row in test))

    def test_group_kfold_does_not_leak_neighborhoods(self) -> None:
        definition, include_311, labeled = attach_labels(_rows())
        self.assertEqual(definition, "pedestrian_crash_nearby")
        self.assertTrue(include_311)
        seen_test = set()
        for train_idx, test_idx in neighborhood_group_kfold(labeled):
            train = [labeled[i] for i in train_idx]
            test = [labeled[i] for i in test_idx]
            assert_disjoint_neighborhoods(train, test)
            seen_test.update(row["id"] for row in test)
        self.assertEqual(seen_test, {row["id"] for row in labeled})


class LearnedScorerTest(unittest.TestCase):
    def test_predicts_finite_scores_on_fixture_rows(self) -> None:
        _, include_311, labeled = attach_labels(_rows())
        scorer = LearnedPriorityScorer(include_311=include_311)
        scorer.fit(labeled)
        scores = scorer.predict_scores(labeled)
        self.assertEqual(len(scores), len(labeled))
        self.assertTrue(np.all(np.isfinite(scores)))
        self.assertTrue(np.all((scores >= 0.0) & (scores <= 1.0)))

    def test_feature_vector_length_matches_include_311_flag(self) -> None:
        row = _rows()[0]
        with_311 = row_to_vector(row, include_311=True)
        without_311 = row_to_vector(row, include_311=False)
        self.assertEqual(with_311.shape, (9,))
        self.assertEqual(without_311.shape, (8,))
        self.assertFalse(math.isnan(float(with_311[-1])))

    def test_composite_label_when_crash_positives_are_scarce(self) -> None:
        rows = []
        for i in range(12):
            rows.append(
                {
                    "id": f"x{i}",
                    "neighborhood_id": "MN0101" if i < 6 else "MN0102",
                    "pedestrian_crash_count": 1 if i == 0 else 0,
                    "pavement_marking_311_count_since_2020": 2 if i in (0, 1, 7) else 0,
                    "paint_missing_ratio": 0.2,
                    "stripe_break_ratio": 0.1,
                    "contrast_score": 0.5,
                    "occlusion_penalty": 0.0,
                    "school_zone": False,
                    "street_width_ft": 40,
                    "approach_street_count": 2,
                }
            )
        definition, include_311, labeled = attach_labels(rows)
        self.assertEqual(definition, "crash_or_311_faded_marking")
        self.assertFalse(include_311)
        self.assertEqual(sum(row["label"] for row in labeled), 3)

    def test_gis_only_feature_vector_drops_image_columns(self) -> None:
        row = {
            "school_zone": True,
            "street_width_ft": 60,
            "approach_street_count": 3,
            "heading_degrees": 10,
            "secondary_heading_degrees": 100,
            "pavement_marking_311_count_since_2020": 4,
            "image_metrics_missing": True,
        }
        vector = row_to_vector(row, include_311=True, include_image=False)
        self.assertEqual(vector.shape, (5,))

    def test_gis_only_ranker_explains_top_features(self) -> None:
        rows = []
        ntas = ["MN0101", "BK0101", "QN0101", "BX0101", "SI0101"]
        for i in range(20):
            rows.append(
                {
                    "id": f"nyc-{i}",
                    "neighborhood_id": ntas[i % 5],
                    "neighborhood_name": ntas[i % 5],
                    "borough": "Manhattan",
                    "pedestrian_crash_count": 1 if i % 2 == 0 else 0,
                    "pavement_marking_311_count_since_2020": 3 if i % 2 == 0 else 0,
                    "school_zone": i % 3 == 0,
                    "street_width_ft": 30 + i,
                    "approach_street_count": 2 + (i % 2),
                    "heading_degrees": 0,
                    "secondary_heading_degrees": 90,
                    "image_metrics_missing": True,
                    "label": 1 if i % 2 == 0 else 0,
                }
            )
        from crosswalk_scoring import rows_have_image_metrics

        self.assertFalse(rows_have_image_metrics(rows))
        scorer = LearnedPriorityScorer(include_311=True, include_image=False)
        scorer.fit(rows)
        scores = scorer.predict_scores(rows)
        self.assertEqual(len(scores), 20)
        self.assertTrue(np.all(np.isfinite(scores)))
        explained = scorer.explain_rows(rows[:1], top_k=3)[0]
        self.assertEqual(len(explained), 3)
        self.assertIn("label", explained[0])
        self.assertIn("contribution", explained[0])


if __name__ == "__main__":
    unittest.main()
