import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from crosswalk_pipeline.live_imagery import (
    ORTHO_YEAR,
    SKIP_IMAGERY_ENV,
    fetch_plottable_imagery,
    plot_image_paths,
    select_imagery_targets,
)


def _rows(n: int = 20) -> list[dict]:
    boroughs = ["Manhattan", "Bronx", "Brooklyn", "Queens", "Staten Island"]
    rows = []
    for i in range(n):
        rows.append(
            {
                "id": f"nyc-test-{i}",
                "intersection_label": f"Street {i} & Avenue {i}",
                "lat": 40.7 + i * 0.001,
                "lon": -74.0 + i * 0.001,
                "borough": boroughs[i % len(boroughs)],
                "model_score": 0.99 - i * 0.01,
                "pedestrian_crash_count": i % 3,
                "year": 2024,
            }
        )
    return rows


class ImageryTargetTest(unittest.TestCase):
    def test_ortho_year_is_newest_published_nyc_layer(self) -> None:
        self.assertEqual(ORTHO_YEAR, 2024)

    def test_default_selects_every_plotted_row(self) -> None:
        rows = _rows(12)
        selected = select_imagery_targets(rows)
        self.assertEqual({row["id"] for row in selected}, {row["id"] for row in rows})
        self.assertEqual(selected[0]["id"], "nyc-test-0")

    def test_subset_keeps_top_scores_and_borough_sample(self) -> None:
        rows = _rows(20)
        selected = select_imagery_targets(rows, top_n=5, extra_n=5)
        self.assertEqual(len(selected), 10)
        top_ids = {row["id"] for row in selected[:5]}
        self.assertEqual(top_ids, {f"nyc-test-{i}" for i in range(5)})
        extra_boroughs = {row["borough"] for row in selected[5:]}
        self.assertGreaterEqual(len(extra_boroughs), 3)

    def test_skip_env_does_not_fetch(self) -> None:
        rows = _rows(3)
        with patch.dict(os.environ, {SKIP_IMAGERY_ENV: "1"}):
            with patch("crosswalk_pipeline.live_imagery.fetch_plottable_crop") as mocked:
                result = fetch_plottable_imagery(rows)
        self.assertEqual(result, {})
        mocked.assert_not_called()


class ImageryCacheTest(unittest.TestCase):
    def test_existing_jpegs_are_reused_without_network(self) -> None:
        from crosswalk_pipeline.live_imagery import fetch_plottable_crop
        from crosswalk_pipeline.models import candidate_from_dict

        row = _rows(1)[0]
        candidate = candidate_from_dict(row)
        with tempfile.TemporaryDirectory() as tmp:
            images_dir = Path(tmp)
            full_path, thumb_path = plot_image_paths(candidate.id, images_dir)
            Image.new("RGB", (32, 24), (255, 80, 0)).save(full_path, format="JPEG")
            Image.new("RGB", (16, 12), (255, 80, 0)).save(thumb_path, format="JPEG")
            with patch("crosswalk_pipeline.live_imagery.PATHS") as paths:
                paths.processed_images_dir = images_dir
                with patch("crosswalk_pipeline.live_imagery._fetch_crop") as mocked_fetch:
                    metrics = fetch_plottable_crop(candidate)
            mocked_fetch.assert_not_called()
            self.assertEqual(metrics.image_path, str(full_path))
            self.assertTrue(Path(metrics.thumbnail_path).exists())


class SnapshotImageryContractTest(unittest.TestCase):
    def test_committed_snapshot_documents_imagery_fields(self) -> None:
        root = Path(__file__).resolve().parents[3]
        records = json.loads((root / "data" / "export" / "crosswalks.json").read_text())
        meta = json.loads((root / "data" / "export" / "meta.json").read_text())
        self.assertGreater(len(records), 0)
        self.assertIn("image_url", records[0])
        self.assertIn("thumbnail_url", records[0])
        if meta.get("n_with_imagery"):
            self.assertGreater(int(meta["n_with_imagery"]), 0)
            self.assertTrue(any(row.get("image_url") for row in records))
            self.assertIn("plotted", str(meta.get("imagery_rule") or "").lower())
            self.assertEqual(int(meta.get("imagery_year") or 0), 2024)
            self.assertNotIn("2026 coming", str(meta.get("imagery_rule") or "").lower())


if __name__ == "__main__":
    unittest.main()
