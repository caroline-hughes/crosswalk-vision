import tempfile
import unittest
from pathlib import Path

from crosswalk_pipeline.artifact_store import LocalArtifactStore


class ArtifactStoreWebPublishTest(unittest.TestCase):
    def test_full_crops_stay_out_of_web_public(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = LocalArtifactStore(
                export_dir=root / "export",
                web_images_dir=root / "web-images",
                web_data_dir=root / "web-data",
            )
            crop_url = store.write_crop("nyc-1", b"full", ext="jpg")
            thumb_url = store.write_thumbnail("nyc-1", b"thumb", ext="jpg")

            self.assertEqual(crop_url, "/images/nyc-1.jpg")
            self.assertEqual(thumb_url, "/images/nyc-1-thumb.jpg")
            self.assertTrue((root / "export" / "images" / "nyc-1.jpg").exists())
            self.assertTrue((root / "export" / "images" / "nyc-1-thumb.jpg").exists())
            self.assertFalse((root / "web-images" / "nyc-1.jpg").exists())
            self.assertTrue((root / "web-images" / "nyc-1-thumb.jpg").exists())


if __name__ == "__main__":
    unittest.main()
