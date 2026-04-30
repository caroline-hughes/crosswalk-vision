import unittest

from crosswalk_scoring import HeuristicCrosswalkScorer, ScoringInput


class HeuristicCrosswalkScorerTest(unittest.TestCase):
    def test_score_generates_expected_reason_tags(self) -> None:
        scorer = HeuristicCrosswalkScorer()
        result = scorer.score(
            ScoringInput(
                id="fixture",
                paint_missing_ratio=0.7,
                stripe_break_ratio=0.5,
                contrast_score=0.2,
                occlusion_penalty=0.1,
                school_zone=True,
                pavement_marking_311_count_since_2020=3,
            )
        )

        self.assertEqual(result.severity_score, 67)
        self.assertEqual(result.confidence_score, 0.9)
        self.assertEqual(result.rank_score, 67.0)
        self.assertEqual(
            result.reason_tags,
            [
                "low contrast",
                "broken stripes",
                "partial paint loss",
                "school zone",
                "311 x3 since 2020",
            ],
        )


if __name__ == "__main__":
    unittest.main()
