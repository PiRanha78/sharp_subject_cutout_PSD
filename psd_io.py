"""Write ComfyUI IMAGE + MASK to a layered PSD (Photoshop) file."""

from __future__ import annotations

import os
from typing import Iterable

import numpy as np
import torch
from PIL import Image


def _require_psd_tools():
    try:
        from psd_tools.api.psd_image import PSDImage
    except ImportError as exc:
        raise ImportError(
            "A PSD mentéshez telepítsd a psd-tools csomagot a ComfyUI Pythonjába:\n"
            "  python_embeded\\python.exe -m pip install psd-tools"
        ) from exc
    return PSDImage


def tensor_to_rgb_uint8(image: torch.Tensor) -> np.ndarray:
    """Single frame IMAGE [H,W,C] float 0..1 -> uint8 RGB."""
    arr = image.detach().cpu().numpy()
    if arr.ndim != 3:
        raise ValueError(f"Expected IMAGE [H,W,C], got shape {arr.shape}")
    channels = arr.shape[-1]
    if channels >= 3:
        rgb = arr[..., :3]
    elif channels == 1:
        rgb = np.repeat(arr, 3, axis=-1)
    else:
        raise ValueError(f"Unsupported channel count: {channels}")
    return (np.clip(rgb, 0.0, 1.0) * 255.0).round().astype(np.uint8)


def tensor_to_mask_uint8(mask: torch.Tensor) -> np.ndarray:
    """Single frame MASK [H,W] or [1,H,W] float 0..1 -> uint8 L (255 = visible)."""
    m = mask.detach().cpu().numpy()
    while m.ndim > 2:
        m = m[0]
    if m.ndim != 2:
        raise ValueError(f"Expected MASK [H,W], got shape {mask.shape}")
    return (np.clip(m, 0.0, 1.0) * 255.0).round().astype(np.uint8)


def psd_path_beside_source(source_path: str) -> str:
    """Hazetomika.jpg -> same folder / Hazetomika_(ComfyUI).psd"""
    source_path = os.path.abspath(source_path.strip().strip('"'))
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"A forrásfájl nem található: {source_path}")
    folder = os.path.dirname(source_path)
    stem = os.path.splitext(os.path.basename(source_path))[0]
    suffix = "_(ComfyUI)"
    if stem.endswith(suffix):
        stem = stem[: -len(suffix)]
    return os.path.join(folder, f"{stem}{suffix}.psd")


def save_psd_with_mask(
    path: str,
    rgb: np.ndarray,
    mask: np.ndarray,
    *,
    layer_name: str = "Subject",
) -> None:
    """Original opaque pixels plus an editable Photoshop layer mask.

    The mask hides the background. Painting the mask in Photoshop reveals the
    original pixels underneath; they are not deleted.
    """
    PSDImage = _require_psd_tools()

    h, w = rgb.shape[:2]
    if mask.shape[:2] != (h, w):
        raise ValueError(f"Mask size {mask.shape[:2]} does not match image {(h, w)}")

    psd = PSDImage.new(mode="RGB", size=(w, h), depth=8)
    layer = psd.create_pixel_layer_from_array(rgb, name=layer_name)
    layer.create_mask(Image.fromarray(mask, mode="L"))

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    psd.save(path)


def save_batch_psd(
    paths: Iterable[str],
    images: torch.Tensor,
    masks: torch.Tensor,
    *,
    layer_name: str,
) -> list[str]:
    """Save each batch item; returns list of written paths."""
    batch = images.shape[0]
    if masks.shape[0] not in (1, batch):
        raise ValueError(f"Mask batch {masks.shape[0]} incompatible with image batch {batch}")

    written: list[str] = []
    path_iter = iter(paths)
    for i in range(batch):
        path = next(path_iter)
        m = masks[i] if masks.shape[0] == batch else masks[0]
        save_psd_with_mask(
            path,
            tensor_to_rgb_uint8(images[i]),
            tensor_to_mask_uint8(m),
            layer_name=layer_name,
        )
        written.append(path)
    return written
