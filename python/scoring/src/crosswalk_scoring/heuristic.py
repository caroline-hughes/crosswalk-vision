from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class ScoringInput:
    id: str
    paint_missing_ratio: float
    stripe_break_ratio: float
    contrast_score: float
    occlusion_penalty: float
    school_zone: bool
    pavement_marking_311_count_since_2020: int


@dataclass(frozen=True)
class ScoredCandidate:
    severity_score: int
    confidence_score: float
    rank_score: float
    reason_tags: List[str]


class HeuristicCrosswalkScorer:
    def __init__(self, confidence_floor: float = 0.55) -> None:
        self.confidence_floor = confidence_floor

    def score(self, scoring_input: ScoringInput, include_complaints: bool = True) -> ScoredCandidate:
        expected_paint_penalty = self._clamp(scoring_input.paint_missing_ratio) * 50.0
        stripe_break_penalty = self._clamp(scoring_input.stripe_break_ratio) * 20.0
        low_contrast_penalty = (1.0 - self._clamp(scoring_input.contrast_score)) * 16.0
        complaint_boost = 0.0
        if include_complaints:
            complaint_boost = min(scoring_input.pavement_marking_311_count_since_2020, 5) * 3.0

        severity_score = round(expected_paint_penalty + stripe_break_penalty + low_contrast_penalty + complaint_boost)
        confidence_score = round(1.0 - self._clamp(scoring_input.occlusion_penalty), 2)
        rank_score = float(severity_score)

        reason_tags: List[str] = []
        if scoring_input.contrast_score <= 0.45:
            reason_tags.append("low contrast")
        if scoring_input.stripe_break_ratio >= 0.35:
            reason_tags.append("broken stripes")
        if scoring_input.paint_missing_ratio >= 0.35:
            reason_tags.append("partial paint loss")
        if scoring_input.school_zone:
            reason_tags.append("school zone")
        if include_complaints and scoring_input.pavement_marking_311_count_since_2020 > 0:
            reason_tags.append(
                f"311 x{scoring_input.pavement_marking_311_count_since_2020} since 2020"
            )

        return ScoredCandidate(
            severity_score=severity_score,
            confidence_score=confidence_score,
            rank_score=rank_score,
            reason_tags=reason_tags,
        )

    def should_include(self, scored_candidate: ScoredCandidate) -> bool:
        return scored_candidate.confidence_score >= self.confidence_floor

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))
