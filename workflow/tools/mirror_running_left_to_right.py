"""Repair a v2 Codex pet atlas by mirroring running-left into running-right.

The animation rows use fixed 192x208 cells.  Mirroring each cell separately
preserves the running cycle order; mirroring the complete row would reverse it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageOps


CELL_WIDTH = 192
CELL_HEIGHT = 208
RUNNING_RIGHT_ROW = 1
RUNNING_LEFT_ROW = 2
FRAME_COUNT = 8


def repair_atlas(path: Path) -> None:
    with Image.open(path) as source:
        atlas = source.convert("RGBA")

    required_size = (CELL_WIDTH * FRAME_COUNT, CELL_HEIGHT * 11)
    if atlas.size != required_size:
        raise ValueError(f"Expected a v2 1536x2288 atlas, got {atlas.size}: {path}")

    for column in range(FRAME_COUNT):
        left_box = (
            column * CELL_WIDTH,
            RUNNING_LEFT_ROW * CELL_HEIGHT,
            (column + 1) * CELL_WIDTH,
            (RUNNING_LEFT_ROW + 1) * CELL_HEIGHT,
        )
        right_box = (
            column * CELL_WIDTH,
            RUNNING_RIGHT_ROW * CELL_HEIGHT,
            (column + 1) * CELL_WIDTH,
            (RUNNING_RIGHT_ROW + 1) * CELL_HEIGHT,
        )
        atlas.paste(ImageOps.mirror(atlas.crop(left_box)), right_box)

    # Codex's atlas validator requires transparent pixels to carry zero RGB.
    # WebP otherwise may leave color data behind alpha=0 during re-encoding.
    pixels = atlas.load()
    for y in range(atlas.height):
        for x in range(atlas.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0 and (red or green or blue):
                pixels[x, y] = (0, 0, 0, 0)

    atlas.save(path, "WEBP", lossless=True, method=6, exact=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("atlas", type=Path, help="v2 WebP atlas to repair in place")
    args = parser.parse_args()
    repair_atlas(args.atlas)


if __name__ == "__main__":
    main()
