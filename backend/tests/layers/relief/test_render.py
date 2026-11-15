import io

import numpy as np
from PIL import Image

from app.core.config import SLOPE_CLASSES
from app.layers.relief.render import walkability_png


def test_walkability_png_colours_and_transparency():
    cls = np.array([[0, 4], [-1, 2]], dtype=np.int8)
    img = Image.open(io.BytesIO(walkability_png(cls, SLOPE_CLASSES)))
    assert img.mode == "RGBA" and img.size == (2, 2)
    assert img.getpixel((0, 0))[:3] == (0x1a, 0x98, 0x50)   # easy_walk
    assert img.getpixel((1, 0))[:3] == (0xd7, 0x30, 0x27)   # impassable
    assert img.getpixel((0, 1))[3] == 0                      # no data -> transparent
    assert img.getpixel((1, 1))[3] > 0
