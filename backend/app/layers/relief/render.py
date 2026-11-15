"""Walkability overlay: one RGBA pixel per grid cell, coloured by slope class."""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

ALPHA = 170  # semi-transparent so the imagery stays visible underneath


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def walkability_png(slope_class: np.ndarray, classes) -> bytes:
    lut = np.zeros((len(classes) + 1, 4), np.uint8)  # last row = no data, fully transparent
    for i, c in enumerate(classes):
        lut[i] = (*_rgb(c.color), ALPHA)
    idx = np.where(slope_class < 0, len(classes), slope_class)
    buf = io.BytesIO()
    Image.fromarray(lut[idx]).save(buf, format="PNG")  # (h, w, 4) uint8 -> RGBA
    return buf.getvalue()
