from __future__ import annotations

import io
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

import numpy as np
import requests
from PIL import Image
from pyproj import Transformer

from .config import (
    ORTHO_LABEL,
    ORTHO_MAPSERVER_EXPORT_URL,
    ORTHO_PREFERRED_NEXT_YEAR,
    ORTHO_SEASON,
    ORTHO_UPGRADE_NOTE,
    ORTHO_YEAR,
    PATHS,
)
from .models import CandidateRecord, candidate_from_dict

_TRANSFORM_4326_TO_3857 = Transformer.from_crs(4326, 3857, always_xy=True)

# Re-export so callers can keep importing from live_imagery.
EXPORT_URL = ORTHO_MAPSERVER_EXPORT_URL
_SESSION = requests.Session()

PLOT_IMAGE_SIZE = (640, 480)
PLOT_THUMB_SIZE = (320, 240)
IMAGERY_TOP_N = 500
IMAGERY_WORKERS = 12
SKIP_IMAGERY_ENV = "CROSSWALK_SKIP_IMAGERY"


@dataclass(frozen=True)
class ImageMetrics:
    paint_missing_ratio: float
    stripe_break_ratio: float
    contrast_score: float
    occlusion_penalty: float
    image_path: str
    thumbnail_path: str


def fetch_and_analyze_candidate_image(candidate: CandidateRecord) -> ImageMetrics:
    PATHS.processed_images_dir.mkdir(parents=True, exist_ok=True)
    full_path = PATHS.processed_images_dir / f"{candidate.id}.png"
    thumb_path = PATHS.processed_images_dir / f"{candidate.id}-thumb.png"

    if full_path.exists() and thumb_path.exists():
        image = Image.open(full_path).convert("RGB")
    else:
        image = _fetch_crop(candidate)
        image.save(full_path, format="PNG")
        image.resize((320, 240), Image.Resampling.LANCZOS).save(thumb_path, format="PNG")

    metrics = _score_intersection_orientations(image, candidate)

    return ImageMetrics(
        paint_missing_ratio=metrics["paint_missing_ratio"],
        stripe_break_ratio=metrics["stripe_break_ratio"],
        contrast_score=metrics["contrast_score"],
        occlusion_penalty=metrics["occlusion_penalty"],
        image_path=str(full_path),
        thumbnail_path=str(thumb_path),
    )


def _fetch_crop(candidate: CandidateRecord, *, size: Tuple[int, int] = (960, 720)) -> Image.Image:
    x, y = _TRANSFORM_4326_TO_3857.transform(candidate.lon, candidate.lat)
    half_width = 36.0
    half_height = 27.0
    bbox = f"{x - half_width},{y - half_height},{x + half_width},{y + half_height}"

    response = _SESSION.get(
        EXPORT_URL,
        params={
            "bbox": bbox,
            "bboxSR": 3857,
            "imageSR": 3857,
            "size": f"{size[0]},{size[1]}",
            "format": "png32",
            "transparent": "false",
            "f": "image",
        },
        timeout=30,
    )
    response.raise_for_status()
    return Image.open(io.BytesIO(response.content)).convert("RGB")


def plot_image_paths(candidate_id: str, images_dir: Path | None = None) -> Tuple[Path, Path]:
    folder = images_dir or PATHS.processed_images_dir
    return folder / f"{candidate_id}.jpg", folder / f"{candidate_id}-thumb.jpg"


def select_imagery_targets(
    plottable: Sequence[Mapping[str, object]],
    *,
    top_n: int = IMAGERY_TOP_N,
    extra_n: int | None = None,
) -> List[dict]:
    """Choose which plotted nodes get a 2024 ortho crop.

    Default extra_n=None fetches every plotted ('in need') node. Pass extra_n to
    take the top scores plus a borough-stratified sample of the rest — never the
    full 56k scored set.
    """
    ranked = sorted(
        (dict(row) for row in plottable),
        key=lambda row: (
            float(row.get("model_score") or 0.0),
            int(row.get("pedestrian_crash_count") or 0),
        ),
        reverse=True,
    )
    if extra_n is None:
        return ranked
    selected = ranked[: max(0, top_n)]
    selected_ids = {str(row["id"]) for row in selected}
    remainder = [row for row in ranked if str(row["id"]) not in selected_ids]
    if extra_n <= 0 or not remainder:
        return selected

    by_borough: Dict[str, List[dict]] = defaultdict(list)
    for row in remainder:
        by_borough[str(row.get("borough") or "Unknown")].append(row)

    sampled: List[dict] = []
    buckets = {name: list(rows) for name, rows in by_borough.items()}
    while len(sampled) < extra_n and buckets:
        progressed = False
        for name in list(buckets):
            rows = buckets[name]
            if not rows:
                buckets.pop(name, None)
                continue
            # Walk each borough list so sample covers high and mid scores, not only the tail.
            index = 0 if len(rows) == 1 else min(len(rows) - 1, max(0, len(rows) // 3))
            sampled.append(rows.pop(index))
            progressed = True
            if len(sampled) >= extra_n:
                break
        if not progressed:
            break
    return selected + sampled


def _metrics_from_image(image: Image.Image, candidate: CandidateRecord, full_path: Path, thumb_path: Path) -> ImageMetrics:
    scored = _score_intersection_orientations(image, candidate)
    return ImageMetrics(
        paint_missing_ratio=scored["paint_missing_ratio"],
        stripe_break_ratio=scored["stripe_break_ratio"],
        contrast_score=scored["contrast_score"],
        occlusion_penalty=scored["occlusion_penalty"],
        image_path=str(full_path),
        thumbnail_path=str(thumb_path),
    )


def resolve_crop_path(candidate_id: str) -> Path | None:
    """Find a committed or processed crop for this node."""
    names = (f"{candidate_id}.jpg", f"{candidate_id}.png")
    folders = (PATHS.web_images_dir, PATHS.processed_images_dir, PATHS.export_dir / "images")
    for folder in folders:
        for name in names:
            path = folder / name
            if path.exists():
                return path
    return None


def analyze_existing_crop(candidate: CandidateRecord) -> ImageMetrics | None:
    crop = resolve_crop_path(candidate.id)
    if crop is None:
        return None
    image = Image.open(crop).convert("RGB")
    thumb = plot_image_paths(candidate.id)[1]
    if not thumb.exists():
        web_thumb = PATHS.web_images_dir / f"{candidate.id}-thumb.jpg"
        thumb = web_thumb if web_thumb.exists() else crop
    return _metrics_from_image(image, candidate, crop, thumb)


def analyze_existing_crops(rows: Sequence[Mapping[str, object]]) -> Dict[str, ImageMetrics]:
    """Compute live_imagery metrics from crops already on disk. No network."""
    results: Dict[str, ImageMetrics] = {}
    for row in rows:
        candidate = candidate_from_dict(dict(row))
        metrics = analyze_existing_crop(candidate)
        if metrics is not None:
            results[candidate.id] = metrics
    return results


def fetch_plottable_crop(candidate: CandidateRecord, *, force: bool = False) -> ImageMetrics:
    """Fetch a 2024 NYS ortho crop for one plotted node. Cached JPEGs are reused and scored."""
    PATHS.processed_images_dir.mkdir(parents=True, exist_ok=True)
    full_path, thumb_path = plot_image_paths(candidate.id)
    if not force and full_path.exists() and thumb_path.exists():
        image = Image.open(full_path).convert("RGB")
        return _metrics_from_image(image, candidate, full_path, thumb_path)
    cached = resolve_crop_path(candidate.id)
    if not force and cached is not None:
        image = Image.open(cached).convert("RGB")
        thumb = thumb_path if thumb_path.exists() else cached
        return _metrics_from_image(image, candidate, cached, thumb)

    image = _fetch_crop(candidate, size=PLOT_IMAGE_SIZE)
    _write_jpeg(image, full_path, quality=78)
    thumb = image.resize(PLOT_THUMB_SIZE, Image.Resampling.LANCZOS)
    _write_jpeg(thumb, thumb_path, quality=72)
    return _metrics_from_image(image, candidate, full_path, thumb_path)


def fetch_plottable_imagery(
    plottable: Sequence[Mapping[str, object]],
    *,
    extra_n: int | None = None,
    top_n: int = IMAGERY_TOP_N,
    max_workers: int = IMAGERY_WORKERS,
    force: bool = False,
) -> Dict[str, ImageMetrics]:
    """Download 2024 ortho crops for the plotted set only. Never the full scored city."""
    if os.environ.get(SKIP_IMAGERY_ENV) == "1":
        return {}
    targets = select_imagery_targets(plottable, top_n=top_n, extra_n=extra_n)
    results: Dict[str, ImageMetrics] = {}
    if not targets:
        return results

    def _one(row: Mapping[str, object]) -> Tuple[str, ImageMetrics | None]:
        candidate = candidate_from_dict(dict(row))
        try:
            return candidate.id, fetch_plottable_crop(candidate, force=force)
        except Exception:
            return candidate.id, None

    workers = max(1, min(max_workers, len(targets)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, row) for row in targets]
        for future in as_completed(futures):
            candidate_id, metrics = future.result()
            if metrics is not None:
                results[candidate_id] = metrics
    return results


def _write_jpeg(image: Image.Image, path: Path, *, quality: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(path, format="JPEG", quality=quality, optimize=True)


def analyze_image_file(path: Path, candidate: CandidateRecord | None = None) -> Dict[str, float]:
    """Score an existing ortho crop. Used for the paint ranker and the visual gate."""
    image = Image.open(path).convert("RGB")
    if candidate is None:
        return _compute_metrics(image)
    return _score_intersection_orientations(image, candidate)


def _compute_metrics(image: Image.Image) -> Dict[str, float]:
    """Absolute-brightness paint metrics so fresh white bars beat faded gray asphalt.

    Relative-only quantiles treat the brightest 10% as paint even when nothing is
    actually white. Absolute floors keep Victory-style intact bars from looking
    as faded as worn gray crossings.
    """
    image_array = np.asarray(image).astype(np.float32)
    height, width, _ = image_array.shape
    y0, y1 = int(height * 0.28), int(height * 0.72)
    x0, x1 = int(width * 0.22), int(width * 0.78)
    region = image_array[y0:y1, x0:x1, :]
    brightness = region.mean(axis=2)
    channel_spread = region.max(axis=2) - region.min(axis=2)

    shadow_threshold = float(np.quantile(brightness, 0.18))
    shadow_mask = (brightness <= shadow_threshold) & (channel_spread <= 24.0)
    usable_mask = ~shadow_mask

    valid_brightness = brightness[usable_mask]
    if valid_brightness.size == 0:
        valid_brightness = brightness.reshape(-1)

    # Crisp thermoplastic is near-white. Relative highlight alone is not enough.
    abs_paint = (brightness >= 168.0) & (channel_spread <= 38.0) & usable_mask
    rel_cut = max(148.0, float(np.quantile(valid_brightness, 0.90)))
    rel_paint = (brightness >= rel_cut) & (channel_spread <= 40.0) & (brightness >= 150.0) & usable_mask
    paint_mask = abs_paint | rel_paint

    crisp_coverage = float(abs_paint.mean())
    mid_coverage = float(paint_mask.mean())
    ideal_coverage = 0.12
    paint_missing_ratio = _clamp((ideal_coverage - crisp_coverage) / ideal_coverage)
    if mid_coverage < 0.045:
        paint_missing_ratio = max(paint_missing_ratio, 0.62)

    column_strength = paint_mask.mean(axis=0)
    if column_strength.size:
        top_slice = np.sort(column_strength)[-max(4, column_strength.size // 12) :]
        stripe_peak_strength = float(top_slice.mean())
    else:
        stripe_peak_strength = 0.0
    stripe_break_ratio = _clamp(1.0 - stripe_peak_strength / 0.34)

    p95 = float(np.quantile(valid_brightness, 0.95))
    p30 = float(np.quantile(valid_brightness, 0.30))
    contrast_raw = (p95 - p30) / 120.0
    if p95 < 160.0:
        contrast_raw *= 0.55
    contrast_score = _clamp(contrast_raw)

    occlusion_penalty = _clamp(float(shadow_mask.mean()) / 0.5)

    return {
        "paint_missing_ratio": round(paint_missing_ratio, 4),
        "stripe_break_ratio": round(stripe_break_ratio, 4),
        "contrast_score": round(contrast_score, 4),
        "occlusion_penalty": round(occlusion_penalty, 4),
    }


def _score_intersection_orientations(image: Image.Image, candidate: CandidateRecord) -> Dict[str, float]:
    headings = [candidate.heading_degrees]
    if candidate.secondary_heading_degrees is not None:
        headings.append(candidate.secondary_heading_degrees)

    scored_options = []
    for heading in headings:
        rotated = image.rotate(90.0 - heading, resample=Image.Resampling.BICUBIC, expand=False)
        metrics = _compute_metrics(rotated)
        proxy = (
            metrics["paint_missing_ratio"] * 50.0
            + metrics["stripe_break_ratio"] * 25.0
            + (1.0 - metrics["contrast_score"]) * 20.0
            - metrics["occlusion_penalty"] * 8.0
        )
        scored_options.append((proxy, metrics))

    scored_options.sort(key=lambda item: item[0], reverse=True)
    return scored_options[0][1]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
