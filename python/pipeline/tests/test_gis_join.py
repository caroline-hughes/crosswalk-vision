import json
import unittest
from pathlib import Path

from crosswalk_pipeline.gis_join import (
    assign_neighborhoods,
    crash_counts_from_join,
    join_events_to_candidates,
    points_within_radius,
)

TINY_NTA = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"NTA2020": "MN0101", "NTAName": "Financial District-Battery Park City"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-74.02, 40.70],
                        [-74.00, 40.70],
                        [-74.00, 40.71],
                        [-74.02, 40.71],
                        [-74.02, 40.70],
                    ]
                ],
            },
        },
        {
            "type": "Feature",
            "properties": {"NTA2020": "MN0102", "NTAName": "Tribeca-Civic Center"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-74.02, 40.71],
                        [-74.00, 40.71],
                        [-74.00, 40.72],
                        [-74.02, 40.72],
                        [-74.02, 40.71],
                    ]
                ],
            },
        },
    ],
}


class FeatureJoinTest(unittest.TestCase):
    def test_crash_join_counts_only_events_within_radius(self) -> None:
        candidates = [
            {"id": "near", "lat": 40.7070, "lon": -74.0110},
            {"id": "far", "lat": 40.7190, "lon": -73.9950},
        ]
        events = [
            {"collision_id": "1", "latitude": 40.70705, "longitude": -74.01105},
            {"collision_id": "2", "latitude": 40.70702, "longitude": -74.01098},
            {"collision_id": "3", "latitude": 40.7189, "longitude": -73.9951},
        ]
        matched = join_events_to_candidates(candidates, events, radius_ft=150.0)
        counts = crash_counts_from_join(matched)
        self.assertEqual(counts["near"], 2)
        self.assertEqual(counts["far"], 1)

    def test_neighborhood_point_in_polygon(self) -> None:
        candidates = [
            {"id": "fidi", "lat": 40.705, "lon": -74.011},
            {"id": "tribeca", "lat": 40.715, "lon": -74.008},
        ]
        assigned = assign_neighborhoods(candidates, TINY_NTA)
        self.assertEqual(assigned["fidi"]["neighborhood_id"], "MN0101")
        self.assertEqual(assigned["tribeca"]["neighborhood_id"], "MN0102")
        self.assertEqual(assigned["fidi"]["neighborhood_name"], "Financial District-Battery Park City")

    def test_school_proximity_flag_varies(self) -> None:
        candidates = [
            {"id": "beside_school", "lat": 40.7128, "lon": -74.0162},
            {"id": "far_from_school", "lat": 40.7024, "lon": -74.0128},
        ]
        schools = [{"latitude": 40.7128, "longitude": -74.0162, "location_name": "P.S. 89"}]
        flagged = points_within_radius(candidates, schools, radius_ft=800.0)
        self.assertTrue(flagged["beside_school"])
        self.assertFalse(flagged["far_from_school"])


class SnapshotContractTest(unittest.TestCase):
    def test_export_snapshot_contains_required_fields(self) -> None:
        root = Path(__file__).resolve().parents[3]
        records = json.loads((root / "data" / "export" / "crosswalks.json").read_text())
        meta = json.loads((root / "data" / "export" / "meta.json").read_text())

        self.assertGreater(len(records), 0)

        first = records[0]
        self.assertEqual(first["year"], 2024)
        for field in (
            "severity_score",
            "confidence_score",
            "rank_score",
            "reason_tags",
            "image_url",
            "thumbnail_url",
            "google_maps_url",
            "model_score",
            "heuristic_score",
            "neighborhood",
            "priority_reason",
            "pedestrian_crash_count",
        ):
            self.assertIn(field, first)

        self.assertIn("New York City", meta["pilot_boundary"])
        self.assertEqual(meta["total_records"], len(records))
        self.assertIn("caveat", meta)
        self.assertIn("scoring_method", meta)
        self.assertGreaterEqual(int(meta.get("n_scored") or len(records)), len(records))
        school_flags = {record["school_zone"] for record in records}
        self.assertTrue(len(school_flags) >= 1)
        self.assertTrue(all(record["leg_label"] for record in records))
        self.assertIn("borough", first)
        self.assertIn("top_features", first)


class Committed311Test(unittest.TestCase):
    def test_committed_311_is_not_the_socrata_default_page(self) -> None:
        root = Path(__file__).resolve().parents[3]
        rows = json.loads((root / "data" / "raw" / "pavement_marking_311.json").read_text())
        self.assertGreater(
            len(rows),
            100,
            "HEAD's 311 dump was the Socrata default page of 100; paginate before committing",
        )


if __name__ == "__main__":
    unittest.main()
