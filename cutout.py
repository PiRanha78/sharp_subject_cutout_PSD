"""Razor-sharp subject cutout for very large images.

The mask from RMBG (and similar nodes) is estimated at ~1–2k and Lanczos-upscaled,
so the silhouette is a wide gray fringe. This module snaps that fringe to the
full-resolution photo edges, then thresholds it to a hard 0/1 mask. No blur,
no geometric circle.
"""

from __future__ import annotations

import cv2
import numpy as np


def _luma(rgb: np.ndarray) -> np.ndarray:
    return (
        rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    ).astype(np.float32)


def guided_filter(guide: np.ndarray, src: np.ndarray, radius: int, eps: float) -> np.ndarray:
    """Grayscale guided filter (He et al.) via box filters. Output stays float32."""
    radius = max(1, int(radius))
    k = 2 * radius + 1
    kernel = (k, k)
    guide = guide.astype(np.float32, copy=False)
    src = src.astype(np.float32, copy=False)
    mean_i = cv2.blur(guide, kernel)
    mean_p = cv2.blur(src, kernel)
    mean_ip = cv2.blur(guide * src, kernel)
    cov = mean_ip - mean_i * mean_p
    mean_ii = cv2.blur(guide * guide, kernel)
    var = mean_ii - mean_i * mean_i
    a = cov / (var + eps)
    b = mean_p - a * mean_i
    mean_a = cv2.blur(a, kernel)
    mean_b = cv2.blur(b, kernel)
    return mean_a * guide + mean_b


def _bounds(mask: np.ndarray, thresh: float, margin: int, height: int, width: int):
    ys, xs = np.nonzero(mask > thresh)
    if len(xs) == 0:
        return None
    y0 = max(0, int(ys.min()) - margin)
    y1 = min(height, int(ys.max()) + 1 + margin)
    x0 = max(0, int(xs.min()) - margin)
    x1 = min(width, int(xs.max()) + 1 + margin)
    return y0, y1, x0, x1


def subject_box(mask: np.ndarray, padding: int) -> tuple[int, int, int, int]:
    """Tight box around the hard mask: x0, y0, x1, y1."""
    height, width = mask.shape[:2]
    found = _bounds(mask, 0.5, int(padding), height, width)
    if found is None:
        return (0, 0, width, height)
    y0, y1, x0, x1 = found
    return (x0, y0, x1, y1)


def _antialiased_contour(
    guide: np.ndarray,
    snapped: np.ndarray,
    threshold: float,
    aa_pixels: float,
) -> np.ndarray:
    """Turn a blocky silhouette into a thin edge that still sits on the photo.

    A hard threshold of an upscaled mask is a staircase. The mask is curved just
    enough to round those steps, pulled back onto the photograph, then converted
    to a coverage ramp only ``aa_pixels`` wide.
    """
    aa = float(aa_pixels)
    if aa <= 0.0:
        return (snapped >= threshold).astype(np.float32)

    sigma = max(1.0, aa)
    radius = max(1, int(np.ceil(sigma * 3.0)))
    curved = cv2.GaussianBlur(snapped, (radius * 2 + 1, radius * 2 + 1), sigmaX=sigma, sigmaY=sigma)
    curved = guided_filter(guide, curved, radius=max(2, int(round(sigma * 2))), eps=1e-4)

    gy, gx = np.gradient(curved.astype(np.float32))
    slope = np.maximum(np.hypot(gx, gy), 1e-3)
    signed = (curved - float(threshold)) / slope
    coverage = 0.5 + signed / aa
    return np.clip(coverage, 0.0, 1.0).astype(np.float32)


def sharpen_subject_mask(
    rgb: np.ndarray,
    mask: np.ndarray,
    *,
    threshold: float = 0.5,
    snap_radius: int = 16,
    padding: int = 8,
    crop_to_subject: bool = True,
    edge_aa_pixels: float = 1.5,
) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]]:
    """
    rgb: float32 HxWx3 in 0..1
    mask: float32 HxW in 0..1 (soft silhouette)

    Returns cropped rgb, hard mask, and box (x0, y0, x1, y1) in the original image.
    """
    height, width = rgb.shape[:2]
    if mask.shape[:2] != (height, width):
        mask = cv2.resize(mask, (width, height), interpolation=cv2.INTER_LINEAR)

    margin = int(snap_radius) * 2 + int(padding) + 2
    coarse = _bounds(mask, 0.02, margin, height, width)
    if coarse is None:
        hard = np.zeros((height, width), dtype=np.float32)
        return rgb, hard, (0, 0, width, height)

    cy0, cy1, cx0, cx1 = coarse
    crop_rgb = rgb[cy0:cy1, cx0:cx1]
    crop_mask = mask[cy0:cy1, cx0:cx1]

    guide = _luma(crop_rgb)
    if snap_radius > 0:
        snapped = guided_filter(guide, crop_mask, snap_radius, eps=1e-4)
    else:
        snapped = crop_mask

    hard = _antialiased_contour(guide, snapped, float(threshold), edge_aa_pixels)

    if not crop_to_subject:
        full = np.zeros((height, width), dtype=np.float32)
        full[cy0:cy1, cx0:cx1] = hard
        return rgb, full, (0, 0, width, height)

    tight = _bounds(hard, 0.5, int(padding), hard.shape[0], hard.shape[1])
    if tight is None:
        full = np.zeros((height, width), dtype=np.float32)
        full[cy0:cy1, cx0:cx1] = hard
        return rgb, full, (0, 0, width, height)

    ty0, ty1, tx0, tx1 = tight
    out_rgb = crop_rgb[ty0:ty1, tx0:tx1]
    out_mask = hard[ty0:ty1, tx0:tx1]
    box = (cx0 + tx0, cy0 + ty0, cx0 + tx1, cy0 + ty1)
    return out_rgb, out_mask, box
