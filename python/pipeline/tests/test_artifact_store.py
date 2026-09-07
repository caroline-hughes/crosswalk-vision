import tempfile
import unittest
from pathlib import Path

from crosswalk_pipeline.artifact_store import LocalArtifactStore
from crosswalk_pipeline.cli import _static_photo_urls


class StaticPhotoUrlTest(unittest.TestCase):
    def test_prefers_thumb_for_both_fields(self) -> None:
        image, thumb = _static_photo_urls("/images/nyc-1.jpg", "/images/nyc-1-thumb.jpg")
        self.assertEqual(image, "/images/nyc-1-thumb.jpg")
        self.assertEqual(thumb, "/images/nyc-1-thumb.jpg")

    def test_rewrites_full_crop_when_thumb_missing(self) -> None:
        image, thumb = _static_photo_urls("/images/nyc-1.jpg", "")
        self.assertEqual((image, thumb), ("/images/nyc-1-thumb.jpg", "/images/nyc-1-thumb.jpg"))


class ArtifactStoreTest(unittest.TestCase):
    def test_full_crop_stays_out_of_the_static_web_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = LocalArtifactStore(
                export_dir=root / "export",
                web_images_dir=root / "web",
                web_data_dir=root / "data",
                processed_images_dir=root / "processed",
            )
            crop_url = store.write_crop("nyc-1", b"full-bytes", ext="jpg")
            thumb_url = store.write_thumbnail("nyc-1", b"thumb-bytes", ext="jpg")
            self.assertEqual(crop_url, "/images/nyc-1.jpg")
            self.assertEqual(thumb_url, "/images/nyc-1-thumb.jpg")
            self.assertFalse((root / "web" / "nyc-1.jpg").exists())
            self.assertTrue((root / "web" / "nyc-1-thumb.jpg").is_file())
            self.assertTrue((root / "processed" / "nyc-1.jpg").is_file())
            self.assertTrue((root / "export" / "images" / "nyc-1.jpg").is_file())


if __name__ == "__main__":
    unittest.main()
