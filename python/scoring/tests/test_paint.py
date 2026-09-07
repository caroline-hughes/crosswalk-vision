import unittest

from crosswalk_scoring import (
    attach_labels,
    image_paint_score,
    looks_faded_heuristic,
    passes_visual_gate,
    remaking_priority,
    visual_gate_threshold,
)


def _row(**overrides) -> dict:
    base = {
        "id": "nyc-test",
        "paint_missing_ratio": 0.7,
        "stripe_break_ratio": 0.6,
        "contrast_score": 0.25,
        "occlusion_penalty": 0.1,
        "image_metrics_missing": False,
        "school_zone": False,
        "pedestrian_crash_count": 0,
        "pavement_marking_311_count_since_2020": 0,
        "street_width_ft": 80,
    }
    base.update(overrides)
    return base


class PaintScoreTest(unittest.TestCase):
    def test_faded_crop_scores_higher_than_fresh_paint(self) -> None:
        faded = image_paint_score(_row())
        fresh = image_paint_score(
            _row(paint_missing_ratio=0.08, stripe_break_ratio=0.05, contrast_score=0.82)
        )
        self.assertGreater(faded, 0.5)
        self.assertLess(fresh, 0.25)
        self.assertGreater(faded, fresh)

    def test_crash_and_width_do_not_change_image_score(self) -> None:
        base = image_paint_score(_row())
        crashy = image_paint_score(_row(pedestrian_crash_count=12, street_width_ft=120, school_zone=True))
        self.assertEqual(base, crashy)

    def test_visual_gate_excludes_good_paint_even_if_crashy(self) -> None:
        fine = _row(
            paint_missing_ratio=0.1,
            stripe_break_ratio=0.08,
            contrast_score=0.8,
            pedestrian_crash_count=9,
            street_width_ft=110,
            pavement_marking_311_count_since_2020=8,
        )
        bad = _row(id="faded")
        threshold = visual_gate_threshold([image_paint_score(fine), image_paint_score(bad)])
        self.assertFalse(passes_visual_gate(fine, threshold=threshold))
        self.assertTrue(passes_visual_gate(bad, threshold=threshold))

    def test_urgency_cannot_promote_good_paint_into_severe(self) -> None:
        fine = _row(
            paint_missing_ratio=0.05,
            stripe_break_ratio=0.04,
            contrast_score=0.85,
            school_zone=True,
            pedestrian_crash_count=8,
        )
        self.assertFalse(looks_faded_heuristic(fine))
        self.assertFalse(passes_visual_gate(fine, threshold=0.42))

    def test_attach_labels_ignores_crash_only_positives(self) -> None:
        definition, include_311, labeled = attach_labels(
            [
                _row(
                    id="wide-crash",
                    paint_missing_ratio=0.05,
                    stripe_break_ratio=0.04,
                    contrast_score=0.86,
                    pedestrian_crash_count=10,
                ),
                _row(id="311", pavement_marking_311_count_since_2020=2, paint_missing_ratio=0.1, contrast_score=0.8),
            ]
        )
        self.assertEqual(definition, "faded_marking_311_or_looks_bad")
        self.assertFalse(include_311)
        by_id = {row["id"]: row["label"] for row in labeled}
        self.assertEqual(by_id["wide-crash"], 0)
        self.assertEqual(by_id["311"], 1)


if __name__ == "__main__":
    unittest.main()
