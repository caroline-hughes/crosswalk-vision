from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class PipelinePaths:
    root: Path = ROOT
    raw_dir: Path = ROOT / "data" / "raw"
    processed_dir: Path = ROOT / "data" / "processed"
    export_dir: Path = ROOT / "data" / "export"
    web_data_dir: Path = ROOT / "apps" / "web" / "public" / "data"
    web_images_dir: Path = ROOT / "apps" / "web" / "public" / "images"
    fixtures_dir: Path = Path(__file__).resolve().parent / "fixtures"


PATHS = PipelinePaths()
