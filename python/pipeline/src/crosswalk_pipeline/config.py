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
    lion_zip_path: Path = ROOT / "data" / "raw" / "nyclion.zip"
    lion_unzipped_dir: Path = ROOT / "data" / "raw" / "nyclion_unzipped"
    lion_gdb_path: Path = ROOT / "data" / "raw" / "nyclion_unzipped" / "lion" / "lion.gdb"
    school_zones_csv_path: Path = ROOT / "data" / "raw" / "school_zones.csv"
    school_locations_path: Path = ROOT / "data" / "raw" / "school_locations.json"
    processed_images_dir: Path = ROOT / "data" / "processed" / "images"
    crashes_path: Path = ROOT / "data" / "raw" / "pedestrian_crashes.json"
    nta_geojson_path: Path = ROOT / "data" / "raw" / "nta_citywide.geojson"
    model_artifact_path: Path = ROOT / "python" / "scoring" / "artifacts" / "priority_ranker.joblib"
    eval_json_path: Path = ROOT / "data" / "export" / "eval_by_neighborhood.json"
    eval_markdown_path: Path = ROOT / "data" / "export" / "eval_by_neighborhood.md"


PATHS = PipelinePaths()

# One-line swap when NYS publishes five-borough coverage for a newer year.
# Today: Spring 2024 (wms/2024). Prefer 2026 once wms/2026 (or equivalent) exists.
ORTHO_YEAR = 2024
ORTHO_PREFERRED_NEXT_YEAR = 2026
ORTHO_SEASON = "Spring"
ORTHO_LABEL = f"{ORTHO_SEASON} {ORTHO_YEAR} NYS ortho"
ORTHO_MAPSERVER_EXPORT_URL = (
    f"https://orthos.its.ny.gov/arcgis/rest/services/wms/{ORTHO_YEAR}/MapServer/export"
)
ORTHO_UPGRADE_NOTE = (
    f"Newest published NYC borough coverage is {ORTHO_SEASON} {ORTHO_YEAR}. "
    f"NYS has {ORTHO_PREFERRED_NEXT_YEAR} on the five-borough flight schedule; "
    f"when wms/{ORTHO_PREFERRED_NEXT_YEAR} (or equivalent NYC coverage) is live "
    f"on orthos.its.ny.gov, refresh plotted-set crops and note any retrain. "
    "Citywide model score is GIS-only and is not computed from these crops."
)
