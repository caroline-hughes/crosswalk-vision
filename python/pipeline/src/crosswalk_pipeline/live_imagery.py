from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import requests
from PIL import Image
from pyproj import Transformer

from .config import PATHS
from .models import CandidateRecord

_TRANSFORM_4326_TO_3857 = Transformer.from_crs(4326, 3857, always_xy=True)

EXPORT_URL = "https://orthos.its.ny.gov/arcgis/rest/services/wms/2024/MapServer/export"
_SESSION = requests.Session()


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


def _fetch_crop(candidate: CandidateRecord) -> Image.Image:
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
            "size": "960,720",
            "format": "png32",
            "transparent": "false",
            "f": "image",
        },
        timeout=120,
    )
    response.raise_for_status()
    return Image.open(io.BytesIO(response.content)).convert("RGB")


def _compute_metrics(image: Image.Image) -> Dict[str, float]:
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

    bright_threshold = float(np.quantile(valid_brightness, 0.9))
    paint_mask = (brightness >= bright_threshold) & (channel_spread <= 44.0) & usable_mask

    coverage = float(paint_mask.mean())
    ideal_coverage = 0.14
    paint_missing_ratio = _clamp((ideal_coverage - coverage) / ideal_coverage if coverage < ideal_coverage else 0.0)

    column_strength = paint_mask.mean(axis=0)
    if column_strength.size:
        top_slice = np.sort(column_strength)[-max(4, column_strength.size // 12) :]
        stripe_peak_strength = float(top_slice.mean())
    else:
        stripe_peak_strength = 0.0
    stripe_break_ratio = _clamp(1.0 - stripe_peak_strength / 0.34)

    contrast_raw = (float(np.quantile(valid_brightness, 0.95)) - float(np.quantile(valid_brightness, 0.35))) / 110.0
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
