import json
import unittest
from pathlib import Path

from crosswalk_pipeline.live_sources import PLOT_MAX, PLOT_PERCENTILE, select_plottable
from crosswalk_scoring import assert_disjoint_neighborhoods, neighborhood_group_kfold


def _citywide_rows() -> list[dict]:
    boroughs = [
        ("Manhattan", "MN0101"),
        ("Bronx", "BX0101"),
        ("Brooklyn", "BK0101"),
        ("Queens", "QN0101"),
        ("Staten Island", "SI0101"),
        ("Manhattan", "MN0201"),
        ("Brooklyn", "BK0201"),
        ("Queens", "QN0201"),
    ]
    rows = []
    for i in range(40):
        borough, nta = boroughs[i % len(boroughs)]
        rows.append(
            {
                "id": f"nyc-{i}",
                "borough": borough,
                "neighborhood_id": nta,
                "label": 1 if i % 2 == 0 else 0,
                "model_score": 0.9 - (i * 0.01),
                "heuristic_score": 10 - (i % 7),
                "pedestrian_crash_count": 1 if i % 3 == 0 else 0,
                "image_metrics_missing": False,
                "paint_missing_ratio": 0.72,
                "stripe_break_ratio": 0.62,
                "contrast_score": 0.22,
                "image_paint_score": 0.68,
            }
        )
    return rows


class CitywideFixtureTest(unittest.TestCase):
    def test_citywide_candidate_fixture_covers_five_boroughs(self) -> None:
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / "src/crosswalk_pipeline/fixtures/citywide_candidates.json").read_text()
        )
        self.assertGreaterEqual(len(payload), 10)
        labels = " ".join(item["intersection_label"] for item in payload)
        self.assertIn("Broadway", labels)
        self.assertIn("Flatbush", labels)
        self.assertIn("Queens", labels)
        self.assertIn("Grand Concourse", labels)
        self.assertIn("Victory", labels)
        lats = [item["lat"] for item in payload]
        lons = [item["lon"] for item in payload]
        self.assertLess(min(lats), 40.62)
        self.assertGreater(max(lats), 40.82)
        self.assertLess(min(lons), -74.10)
        self.assertGreater(max(lons), -73.90)


class PlottableCapTest(unittest.TestCase):
    def test_select_plottable_excludes_good_paint_crashy_rows(self) -> None:
        rows = _citywide_rows()
        rows[0]["id"] = "victory-fine"
        rows[0]["intersection_label"] = "Victory Boulevard & Richmond Avenue"
        rows[0]["paint_missing_ratio"] = 0.08
        rows[0]["stripe_break_ratio"] = 0.05
        rows[0]["contrast_score"] = 0.84
        rows[0]["image_paint_score"] = 0.12
        rows[0]["model_score"] = 0.99
        rows[0]["pedestrian_crash_count"] = 8
        plotted = select_plottable(rows)
        self.assertTrue(all(row["id"] != "victory-fine" for row in plotted))

    def test_select_plottable_caps_and_keeps_borough_floor(self) -> None:
        rows = _citywide_rows()
        plotted = select_plottable(rows)
        self.assertLessEqual(len(plotted), PLOT_MAX)
        self.assertGreater(len(plotted), 0)
        boroughs = {row["borough"] for row in plotted}
        self.assertEqual(
            boroughs, {"Manhattan", "Bronx", "Brooklyn", "Queens", "Staten Island"}
        )
        self.assertGreaterEqual(PLOT_PERCENTILE, 80.0)

    def test_spatial_split_still_disjoint_on_citywide_groups(self) -> None:
        rows = _citywide_rows()
        seen = set()
        for train_idx, test_idx in neighborhood_group_kfold(rows):
            train = [rows[i] for i in train_idx]
            test = [rows[i] for i in test_idx]
            assert_disjoint_neighborhoods(train, test)
            seen.update(row["id"] for row in test)
        self.assertEqual(seen, {row["id"] for row in rows})


class SnapshotContractTest(unittest.TestCase):
    def test_export_snapshot_is_citywide_map_contract(self) -> None:
        root = Path(__file__).resolve().parents[3]
        records_path = root / "data" / "export" / "crosswalks.json"
        meta_path = root / "data" / "export" / "meta.json"
        geojson_path = root / "data" / "export" / "crossings.geojson"
        if not records_path.exists() or not meta_path.exists():
            self.skipTest("export snapshot not built yet")
        records = json.loads(records_path.read_text())
        meta = json.loads(meta_path.read_text())
        self.assertGreater(len(records), 0)
        first = records[0]
        for field in (
            "model_score",
            "heuristic_score",
            "neighborhood",
            "borough",
            "priority_reason",
            "top_features",
            "pedestrian_crash_count",
            "matched_311_complaints",
            "lat",
            "lon",
        ):
            self.assertIn(field, first)
        self.assertIn("New York City", meta["pilot_boundary"])
        self.assertGreaterEqual(int(meta.get("n_scored") or 0), int(meta.get("n_plotted") or 0))
        self.assertEqual(meta["total_records"], len(records))
        self.assertIn("caveat", meta)
        self.assertIn("image_url", first)
        self.assertIn("thumbnail_url", first)
        self.assertIn("paint", meta["scoring_method"].lower())
        self.assertIn("visual", str(meta.get("plot_rule") or "").lower())
        self.assertNotIn("detector", meta["scoring_method"].lower().replace("not a vision detector", ""))
        self.assertIn("not a vision detector", meta["scoring_method"].lower())
        school_flags = {record["school_zone"] for record in records}
        self.assertTrue(school_flags <= {True, False})
        boroughs = {record["borough"] for record in records}
        self.assertTrue({"Manhattan", "Bronx", "Brooklyn", "Queens", "Staten Island"} <= boroughs)
        self.assertNotIn("Unknown", boroughs)
        self.assertTrue(all("unnamed" not in record["intersection_label"].lower() for record in records))
        self.assertFalse(
            any(
                record["intersection_label"] == "Victory Boulevard & Richmond Avenue"
                for record in records
            ),
            "intact-looking Victory Blvd must not pass the visual paint gate",
        )
        school_flags = {record["school_zone"] for record in records}
        self.assertEqual(school_flags, {True, False}, "Near-school filter must not be a no-op")
        self.assertGreater(int(meta.get("n_scored") or 0), int(meta.get("n_plotted") or 0))
        if geojson_path.exists():
            geojson = json.loads(geojson_path.read_text())
            self.assertEqual(geojson["type"], "FeatureCollection")
            self.assertEqual(len(geojson["features"]), len(records))
            props = geojson["features"][0]["properties"]
            self.assertIn("model_score", props)
            self.assertIn("top_features", props)
            self.assertIn("priority_reason", props)
            if first.get("image_url") or first.get("thumbnail_url"):
                self.assertIn("image_url", props)
                self.assertIn("thumbnail_url", props)


if __name__ == "__main__":
    unittest.main()
