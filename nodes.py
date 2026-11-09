import os

import folder_paths
import nodes as comfy_nodes
import numpy as np
import torch

from .circle_math import (
    circle_bounding_box,
    circle_mask_crop,
    circle_mask_full,
    fit_circle_from_mask,
    resolve_center,
    resolve_radius,
)
from .cutout import sharpen_subject_mask, subject_box
from .psd_io import psd_path_beside_source, save_psd_with_mask, tensor_to_mask_uint8, tensor_to_rgb_uint8


def _parse_hex_color(hex_color: str) -> tuple[float, float, float]:
    s = (hex_color or "#000000").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return (0.0, 0.0, 0.0)
    r = int(s[0:2], 16) / 255.0
    g = int(s[2:4], 16) / 255.0
    b = int(s[4:6], 16) / 255.0
    return (r, g, b)


class PreciseCircleMask:
    """Full-resolution circular mask via signed distance (optional sub-pixel AA)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "center_x": ("FLOAT", {"default": 50.0, "min": 0.0, "max": 100.0, "step": 0.01}),
                "center_y": ("FLOAT", {"default": 50.0, "min": 0.0, "max": 100.0, "step": 0.01}),
                "radius": ("FLOAT", {"default": 45.0, "min": 0.0, "max": 100.0, "step": 0.01}),
                "coordinates": (["percent", "pixels"],),
                "radius_mode": (["percent_min_side", "percent_max_side", "pixels"],),
                "edge_aa_pixels": (
                    "FLOAT",
                    {
                        "default": 0.0,
                        "min": 0.0,
                        "max": 4.0,
                        "step": 0.05,
                        "tooltip": "0 = hard edge. ~1 = one pixel anti-alias without blur filters.",
                    },
                ),
            }
        }

    RETURN_TYPES = ("MASK",)
    RETURN_NAMES = ("mask",)
    FUNCTION = "build_mask"
    CATEGORY = "image/crop"

    def build_mask(
        self,
        image,
        center_x,
        center_y,
        radius,
        coordinates,
        radius_mode,
        edge_aa_pixels,
    ):
        _, h, w, _ = image.shape
        cx, cy = resolve_center(w, h, center_x, center_y, coordinates == "percent")
        r = resolve_radius(w, h, radius, radius_mode)
        mask_np = circle_mask_full(w, h, cx, cy, r, edge_aa=edge_aa_pixels)
        return (torch.from_numpy(mask_np),)


class PreciseCircleCrop:
    """Crop square bounds around the circle; only that region is allocated (10k+ friendly)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "center_x": ("FLOAT", {"default": 50.0, "min": 0.0, "max": 100.0, "step": 0.01}),
                "center_y": ("FLOAT", {"default": 50.0, "min": 0.0, "max": 100.0, "step": 0.01}),
                "radius": ("FLOAT", {"default": 45.0, "min": 0.0, "max": 100.0, "step": 0.01}),
                "coordinates": (["percent", "pixels"],),
                "radius_mode": (["percent_min_side", "percent_max_side", "pixels"],),
                "edge_aa_pixels": (
                    "FLOAT",
                    {"default": 0.0, "min": 0.0, "max": 4.0, "step": 0.05},
                ),
                "background_color": ("STRING", {"default": "#000000"}),
                "square_output": ("BOOLEAN", {"default": True}),
                "radius_scale": (
                    "FLOAT",
                    {
                        "default": 1.0,
                        "min": 0.01,
                        "max": 10.0,
                        "step": 0.01,
                        "tooltip": "Csak fit_mask esetén: sugár szorzó az RMBG maszk területéből.",
                    },
                ),
            },
            "optional": {
                "fit_mask": ("MASK",),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "BOX")
    RETURN_NAMES = ("image", "mask", "crop_box")
    FUNCTION = "crop_circle"
    CATEGORY = "image/crop"

    def crop_circle(
        self,
        image,
        center_x,
        center_y,
        radius,
        coordinates,
        radius_mode,
        edge_aa_pixels,
        background_color,
        square_output,
        radius_scale,
        fit_mask=None,
    ):
        batch = image.shape[0]
        _, h, w, c = image.shape
        if fit_mask is not None:
            m = fit_mask[0].detach().cpu().numpy()
            if m.shape[0] != h or m.shape[1] != w:
                raise ValueError(
                    f"fit_mask size {m.shape[1]}x{m.shape[0]} != image size {w}x{h}"
                )
            cx, cy, r = fit_circle_from_mask(m, radius_scale)
        else:
            cx, cy = resolve_center(w, h, center_x, center_y, coordinates == "percent")
            r = resolve_radius(w, h, radius, radius_mode)
        x0, y0, x1, y1 = circle_bounding_box(w, h, cx, cy, r, pad=1)

        if square_output:
            side = max(x1 - x0, y1 - y0)
            half = side // 2
            cx_i, cy_i = int(round(cx)), int(round(cy))
            x0 = max(0, cx_i - half)
            y0 = max(0, cy_i - half)
            x1 = min(w, x0 + side)
            y1 = min(h, y0 + side)
            if x1 - x0 < side:
                x0 = max(0, x1 - side)
            if y1 - y0 < side:
                y0 = max(0, y1 - side)

        crop_w, crop_h = x1 - x0, y1 - y0
        cx_l, cy_l = cx - x0, cy - y0
        mask_np = circle_mask_crop(crop_w, crop_h, cx_l, cy_l, r, edge_aa=edge_aa_pixels)
        mask_t = torch.from_numpy(mask_np)

        bg = torch.tensor(_parse_hex_color(background_color), dtype=image.dtype, device=image.device)
        out_images = []
        out_masks = []
        for i in range(batch):
            crop = image[i, y0:y1, x0:x1, :]
            m = mask_t.to(device=crop.device, dtype=crop.dtype)
            if m.ndim == 2:
                m3 = m.unsqueeze(-1)
            else:
                m3 = m
            comp = crop * m3 + bg.view(1, 1, 3) * (1.0 - m3)
            out_images.append(comp.unsqueeze(0))
            out_masks.append(m.unsqueeze(0))

        return (torch.cat(out_images, dim=0), torch.cat(out_masks, dim=0), [x0, y0, x1, y1])


class PreciseCircleFromMask:
    """Fit circle to an existing mask (centroid + equivalent area radius)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mask": ("MASK",),
                "radius_scale": ("FLOAT", {"default": 1.0, "min": 0.01, "max": 10.0, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("FLOAT", "FLOAT", "FLOAT", "INT", "INT")
    RETURN_NAMES = ("center_x_px", "center_y_px", "radius_px", "width", "height")
    FUNCTION = "fit_circle"
    CATEGORY = "image/crop"

    def fit_circle(self, mask, radius_scale):
        m = mask[0].detach().cpu().numpy()
        h, w = m.shape
        cx, cy, r = fit_circle_from_mask(m, radius_scale)
        return (cx, cy, r, w, h)


class LoadImageSource(comfy_nodes.LoadImage):
    """Load an image and also return the absolute path of the source file."""

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "source_path")
    FUNCTION = "load_image_source"
    CATEGORY = "image"

    def load_image_source(self, image):
        source_path = folder_paths.get_annotated_filepath(image)
        loaded = self.load_image(image)
        return (loaded[0], loaded[1], source_path)


class SaveCircleCropPSD:
    """Save the original image with an editable outline mask beside the source file."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {"tooltip": "Az eredeti kép, változatlan pixelekkel."}),
                "mask": ("MASK", {"tooltip": "A figura körvonala. Fehér = látható, a takart pixelek megmaradnak."}),
                "source_path": ("STRING", {"default": "", "tooltip": "A betöltött forrásfájl teljes útvonala."}),
                "layer_name": ("STRING", {"default": "Original"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("saved_path",)
    FUNCTION = "save_psd"
    OUTPUT_NODE = True
    CATEGORY = "image/crop"

    def save_psd(self, image, mask, source_path, layer_name):
        if mask.ndim == 2:
            mask = mask.unsqueeze(0)
        if image.shape[0] != 1:
            raise ValueError("Egyszerre egy képet ments PSD-be.")
        if mask.shape[-2:] != image.shape[1:3]:
            raise ValueError(
                f"A maszk mérete {mask.shape[-1]}x{mask.shape[-2]} nem egyezik a kép méretével "
                f"{image.shape[2]}x{image.shape[1]}. A kivágásnál kapcsold ki a crop_to_subject opciót, "
                "vagy a PSD-be az eredeti képet kösd."
            )

        path = psd_path_beside_source(source_path)
        rgb = image[0]
        if rgb.shape[-1] > 3:
            rgb = rgb[..., :3]
        save_psd_with_mask(
            path,
            tensor_to_rgb_uint8(rgb),
            tensor_to_mask_uint8(mask[0]),
            layer_name=layer_name or "Original",
        )
        print(f"PSD mentve az eredeti kép mellé: {path}")
        return {"ui": {"text": [path]}, "result": (path,)}


class SharpSubjectCutout:
    """Snap a soft subject mask onto the full-resolution photo edge, then hard-cut it.

    This follows the person's outline. It does not draw a geometric circle.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mask": ("MASK",),
                "threshold": (
                    "FLOAT",
                    {
                        "default": 0.5,
                        "min": 0.05,
                        "max": 0.95,
                        "step": 0.01,
                        "tooltip": "Kemény vágás küszöbe a kontúr illesztése után. 0.5 = a sziluett közepe.",
                    },
                ),
                "snap_radius": (
                    "INT",
                    {
                        "default": 16,
                        "min": 0,
                        "max": 128,
                        "step": 1,
                        "tooltip": "Hány pixelen belül húzza a lágy maszkot a fotó valódi élére. 0 = csak küszöb, blur nélkül.",
                    },
                ),
                "padding": (
                    "INT",
                    {
                        "default": 8,
                        "min": 0,
                        "max": 4096,
                        "step": 1,
                        "tooltip": "Ráhagyás pixelben a figura befoglaló téglalapja körül.",
                    },
                ),
                "background_color": (
                    "STRING",
                    {
                        "default": "#000000",
                        "tooltip": "Nem kerül a fájlba. A PSD háttere átlátszó, a maszk üti ki.",
                    },
                ),
                "crop_to_subject": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": "Csak az előnézeti képet vágja a figura köré. A maszk teljes méretű marad, a PSD-be az eredeti kép kerül.",
                    },
                ),
                "edge_aa_pixels": (
                    "FLOAT",
                    {
                        "default": 1.5,
                        "min": 0.0,
                        "max": 4.0,
                        "step": 0.1,
                        "tooltip": "A lépcsős kontúr kisimítása. 0 = kemény, pixeles él. 1.5 = éles, de nem kockás. Nagyobb érték szélesebb átmenet.",
                    },
                ),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK", "BOX")
    RETURN_NAMES = ("image", "mask", "crop_box")
    FUNCTION = "cut_out"
    CATEGORY = "image/crop"

    def cut_out(self, image, mask, threshold, snap_radius, padding, background_color, crop_to_subject, edge_aa_pixels):
        if mask.ndim == 2:
            mask = mask.unsqueeze(0)
        del background_color
        batch = image.shape[0]
        out_images = []
        out_masks = []
        box = [0, 0, int(image.shape[2]), int(image.shape[1])]
        for i in range(batch):
            rgb = image[i].detach().float().cpu().numpy()
            m = mask[i if i < mask.shape[0] else 0].detach().float().cpu().numpy()
            full_rgb, full_mask, _ = sharpen_subject_mask(
                rgb,
                m,
                threshold=threshold,
                snap_radius=snap_radius,
                padding=0,
                crop_to_subject=False,
                edge_aa_pixels=edge_aa_pixels,
            )
            full_t = torch.from_numpy(np.ascontiguousarray(full_rgb[..., :3]))
            full_hard = torch.from_numpy(np.ascontiguousarray(full_mask))
            if crop_to_subject:
                x0, y0, x1, y1 = subject_box(full_mask, padding)
                preview_rgb = full_t[y0:y1, x0:x1]
                preview_a = full_hard[y0:y1, x0:x1]
                box = [x0, y0, x1, y1]
            else:
                preview_rgb = full_t
                preview_a = full_hard
                box = [0, 0, int(full_t.shape[1]), int(full_t.shape[0])]
            rgba = torch.cat([preview_rgb, preview_a.unsqueeze(-1)], dim=-1)
            out_images.append(rgba.unsqueeze(0))
            out_masks.append(full_hard.unsqueeze(0))

        return (torch.cat(out_images, dim=0), torch.cat(out_masks, dim=0), box)


NODE_CLASS_MAPPINGS = {
    "PreciseCircleMask": PreciseCircleMask,
    "PreciseCircleCrop": PreciseCircleCrop,
    "PreciseCircleFromMask": PreciseCircleFromMask,
    "LoadImageSource": LoadImageSource,
    "SharpSubjectCutout": SharpSubjectCutout,
    "SaveCircleCropPSD": SaveCircleCropPSD,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PreciseCircleMask": "Precise Circle Mask (HQ)",
    "PreciseCircleCrop": "Precise Circle Crop (HQ)",
    "PreciseCircleFromMask": "Precise Circle From Mask",
    "LoadImageSource": "Load Image (Source Path)",
    "SharpSubjectCutout": "Sharp Subject Cutout",
    "SaveCircleCropPSD": "Save Cutout as PSD",
}
