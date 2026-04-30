from __future__ import annotations

import math
import struct
import zlib
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from .models import CandidateRecord

Color = Tuple[int, int, int]


@dataclass(frozen=True)
class RasterCanvas:
    width: int
    height: int
    pixels: List[List[Color]]


def create_crosswalk_crop(candidate: CandidateRecord, width: int = 960, height: int = 720) -> bytes:
    canvas = _new_canvas(width, height, (59, 69, 81))
    road_center_x = width // 2
    road_width = int(width * 0.38)
    road_left = road_center_x - road_width // 2
    road_right = road_center_x + road_width // 2

    _fill_rect(canvas, 0, 0, road_left, height, (102, 121, 92))
    _fill_rect(canvas, road_right, 0, width, height, (97, 112, 89))
    _fill_rect(canvas, road_left, 0, road_right, height, (83, 90, 97))
    _draw_lane_markings(canvas, road_left, road_right)
    _draw_crosswalk(canvas, candidate, road_left, road_right)
    _draw_building_edges(canvas, road_left, road_right)
    _draw_occlusion(canvas, candidate, road_left, road_right)

    return _encode_png(canvas)


def create_thumbnail(candidate: CandidateRecord, width: int = 320, height: int = 240) -> bytes:
    return create_crosswalk_crop(candidate, width=width, height=height)


def _new_canvas(width: int, height: int, color: Color) -> RasterCanvas:
    return RasterCanvas(width=width, height=height, pixels=[[color for _ in range(width)] for _ in range(height)])


def _fill_rect(canvas: RasterCanvas, x0: int, y0: int, x1: int, y1: int, color: Color) -> None:
    for y in range(max(0, y0), min(canvas.height, y1)):
        row = canvas.pixels[y]
        for x in range(max(0, x0), min(canvas.width, x1)):
            row[x] = color


def _draw_lane_markings(canvas: RasterCanvas, road_left: int, road_right: int) -> None:
    center_x = (road_left + road_right) // 2
    for y in range(40, canvas.height - 40, 64):
        _fill_rect(canvas, center_x - 3, y, center_x + 3, min(y + 26, canvas.height), (235, 197, 83))


def _draw_crosswalk(canvas: RasterCanvas, candidate: CandidateRecord, road_left: int, road_right: int) -> None:
    stripe_count = 7
    stripe_gap = 12
    stripe_width = max(18, (road_right - road_left - 40) // stripe_count - stripe_gap)
    start_x = road_left + 20
    base_y = canvas.height // 2 - 120
    stripe_height = 240

    brightness = int(120 + candidate.contrast_score * 120)
    full_color = (brightness, brightness, brightness)
    missing_ratio = candidate.paint_missing_ratio
    break_ratio = candidate.stripe_break_ratio

    for index in range(stripe_count):
        x0 = start_x + index * (stripe_width + stripe_gap)
        x1 = x0 + stripe_width
        active_fraction = max(0.0, 1.0 - missing_ratio)
        stripe_visible_height = int(stripe_height * active_fraction)
        stripe_y0 = base_y + (stripe_height - stripe_visible_height) // 2
        stripe_y1 = stripe_y0 + stripe_visible_height
        _fill_rect(canvas, x0, stripe_y0, x1, stripe_y1, full_color)

        if break_ratio > 0:
            gaps = max(1, int(round(break_ratio * 3)))
            gap_height = max(18, int((stripe_visible_height / max(1, gaps + 1)) * 0.35))
            for gap_index in range(gaps):
                gap_y = stripe_y0 + int((gap_index + 1) * stripe_visible_height / (gaps + 1)) - gap_height // 2
                _fill_rect(canvas, x0, gap_y, x1, gap_y + gap_height, (83, 90, 97))


def _draw_building_edges(canvas: RasterCanvas, road_left: int, road_right: int) -> None:
    _fill_rect(canvas, 0, 0, road_left - 18, 38, (62, 71, 63))
    _fill_rect(canvas, road_right + 18, canvas.height - 52, canvas.width, canvas.height, (62, 71, 63))


def _draw_occlusion(canvas: RasterCanvas, candidate: CandidateRecord, road_left: int, road_right: int) -> None:
    occlusion_count = int(round(candidate.occlusion_penalty * 5))
    if occlusion_count <= 0:
        return

    for index in range(occlusion_count):
        x0 = road_left + 30 + index * 48
        y0 = canvas.height // 2 - 90 + index * 28
        _fill_rect(canvas, x0, y0, min(x0 + 58, road_right - 10), y0 + 28, (42, 45, 54))


def _encode_png(canvas: RasterCanvas) -> bytes:
    raw_rows = []
    for row in canvas.pixels:
        raw_rows.append(b"\x00" + bytes(channel for pixel in row for channel in pixel))

    compressed = zlib.compress(b"".join(raw_rows), level=9)
    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            _chunk(b"IHDR", struct.pack(">IIBBBBB", canvas.width, canvas.height, 8, 2, 0, 0, 0)),
            _chunk(b"IDAT", compressed),
            _chunk(b"IEND", b""),
        ]
    )


def _chunk(chunk_type: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + chunk_type
        + payload
        + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    )
