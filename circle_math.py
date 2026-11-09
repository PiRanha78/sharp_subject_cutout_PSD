"""Distance-based circular masks for very large images (tile-friendly, no blur filters)."""

from __future__ import annotations

import math
from typing import Tuple

import numpy as np

TILE_DEFAULT = 512


def resolve_center(
    width: int,
    height: int,
    center_x: float,
    center_y: float,
    use_percent: bool,
) -> Tuple[float, float]:
    if use_percent:
        return (center_x * 0.01 * width, center_y * 0.01 * height)
    return (float(center_x), float(center_y))


def resolve_radius(
    width: int,
    height: int,
    radius: float,
    radius_mode: str,
) -> float:
    if radius_mode == "pixels":
        return max(0.0, float(radius))
    ref = min(width, height) if radius_mode == "percent_min_side" else max(width, height)
    return max(0.0, radius * 0.01 * ref)


def circle_bounding_box(
    width: int,
    height: int,
    cx: float,
    cy: float,
    radius: float,
    pad: int = 0,
) -> Tuple[int, int, int, int]:
    x0 = max(0, int(math.floor(cx - radius)) - pad)
    y0 = max(0, int(math.floor(cy - radius)) - pad)
    x1 = min(width, int(math.ceil(cx + radius)) + pad)
    y1 = min(height, int(math.ceil(cy + radius)) + pad)
    if x1 <= x0:
        x1 = min(width, x0 + 1)
    if y1 <= y0:
        y1 = min(height, y0 + 1)
    return x0, y0, x1, y1


def _write_circle_block(
    out: np.ndarray,
    y0: int,
    y1: int,
    x0: int,
    x1: int,
    cx: float,
    cy: float,
    radius: float,
    edge_aa: float,
) -> None:
    ys = np.arange(y0, y1, dtype=np.float32)[:, None]
    xs = np.arange(x0, x1, dtype=np.float32)[None, :]
    dist = np.hypot(xs - cx, ys - cy)
    if edge_aa <= 0.0:
        block = dist <= radius
        out[y0:y1, x0:x1] = block.astype(np.float32)
        return
    # Single-pixel (or sub-pixel) analytic AA — no resize / Gaussian blur.
    block = np.clip((radius + edge_aa * 0.5 - dist) / edge_aa, 0.0, 1.0)
    out[y0:y1, x0:x1] = block.astype(np.float32)


def circle_mask_full(
    width: int,
    height: int,
    cx: float,
    cy: float,
    radius: float,
    edge_aa: float = 0.0,
    tile: int = TILE_DEFAULT,
) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.float32)
    if radius <= 0.0:
        return mask
    tile = max(32, int(tile))
    for y0 in range(0, height, tile):
        y1 = min(height, y0 + tile)
        for x0 in range(0, width, tile):
            x1 = min(width, x0 + tile)
            _write_circle_block(mask, y0, y1, x0, x1, cx, cy, radius, edge_aa)
    return mask


def circle_mask_crop(
    crop_w: int,
    crop_h: int,
    cx_local: float,
    cy_local: float,
    radius: float,
    edge_aa: float = 0.0,
    tile: int = TILE_DEFAULT,
) -> np.ndarray:
    return circle_mask_full(crop_w, crop_h, cx_local, cy_local, radius, edge_aa, tile=tile)


def fit_circle_from_mask(mask: np.ndarray, radius_scale: float = 1.0) -> Tuple[float, float, float]:
    """Centroid + equivalent-area circle radius from a binary/soft mask [H,W]."""
    h, w = mask.shape
    ys, xs = np.nonzero(mask > 0.5)
    if len(xs) == 0:
        return (w * 0.5, h * 0.5, 0.0)
    cx = float(xs.mean())
    cy = float(ys.mean())
    area = float(len(xs))
    r = math.sqrt(area / math.pi) * radius_scale
    return (cx, cy, r)
