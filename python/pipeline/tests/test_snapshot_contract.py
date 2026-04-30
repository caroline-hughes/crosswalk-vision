import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class SnapshotContractTest(unittest.TestCase):
    def test_export_snapshot_contains_required_fields(self) -> None:
        records = json.loads((ROOT / "data" / "export" / "crosswalks.json").read_text())
        meta = json.loads((ROOT / "data" / "export" / "meta.json").read_text())

        self.assertGreater(len(records), 0)

        first = records[0]
        self.assertEqual(first["year"], 2024)
        self.assertIn("severity_score", first)
        self.assertIn("confidence_score", first)
        self.assertIn("rank_score", first)
        self.assertIn("reason_tags", first)
        self.assertIn("image_url", first)
        self.assertIn("thumbnail_url", first)
        self.assertIn("google_maps_url", first)

        self.assertEqual(meta["pilot_boundary"], "Lower Manhattan south of Canal Street")
        self.assertEqual(meta["total_records"], len(records))


if __name__ == "__main__":
    unittest.main()
