#!/usr/bin/env python3
"""Repair running-right from running-left without unsafe implicit overwrites."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

CELL_WIDTH = 192
CELL_HEIGHT = 208
RUNNING_RIGHT_ROW = 1
RUNNING_LEFT_ROW = 2
FRAME_COUNT = 8
EXPECTED_SIZE = (CELL_WIDTH * FRAME_COUNT, CELL_HEIGHT * 11)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def repair_image(source: Image.Image) -> Image.Image:
    atlas = source.convert("RGBA")
    if atlas.size != EXPECTED_SIZE:
        raise ValueError(f"expected a v2 1536x2288 atlas, got {atlas.size}")
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
    pixels = atlas.load()
    for y in range(atlas.height):
        for x in range(atlas.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0 and (red or green or blue):
                pixels[x, y] = (0, 0, 0, 0)
    return atlas


def assert_mirrors(atlas: Image.Image) -> None:
    for column in range(FRAME_COUNT):
        left = atlas.crop(
            (
                column * CELL_WIDTH,
                RUNNING_LEFT_ROW * CELL_HEIGHT,
                (column + 1) * CELL_WIDTH,
                (RUNNING_LEFT_ROW + 1) * CELL_HEIGHT,
            )
        )
        right = atlas.crop(
            (
                column * CELL_WIDTH,
                RUNNING_RIGHT_ROW * CELL_HEIGHT,
                (column + 1) * CELL_WIDTH,
                (RUNNING_RIGHT_ROW + 1) * CELL_HEIGHT,
            )
        )
        if ImageChops.difference(right, ImageOps.mirror(left)).getbbox() is not None:
            raise ValueError(f"mirror verification failed at frame {column}")


def save_webp_atomic(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    image.save(temporary, "WEBP", lossless=True, method=6, exact=True)
    temporary.replace(path)


def repair_atlas(
    source_path: Path,
    output_path: Path,
    expected_source_sha256: str | None = None,
    backup_path: Path | None = None,
    force: bool = False,
) -> dict:
    source_path = source_path.resolve()
    output_path = output_path.resolve()
    source_hash = sha256(source_path)
    if expected_source_sha256 and source_hash != expected_source_sha256.upper():
        raise ValueError("source atlas SHA-256 does not match --expected-source-sha256")
    in_place = source_path == output_path
    if in_place and backup_path is None:
        raise ValueError("in-place repair requires --backup")
    if not in_place and output_path.exists() and not force:
        raise ValueError(f"output already exists; pass --force to replace it: {output_path}")
    if in_place:
        backup_path = backup_path.resolve()
        if backup_path == source_path:
            raise ValueError("--backup must differ from the source atlas")
        if backup_path.exists():
            if sha256(backup_path) != source_hash:
                raise ValueError(f"immutable backup already exists and differs: {backup_path}")
        else:
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, backup_path)

    with Image.open(source_path) as opened:
        repaired = repair_image(opened)
    assert_mirrors(repaired)
    save_webp_atomic(repaired, output_path)
    with Image.open(output_path) as verified:
        assert_mirrors(verified.convert("RGBA"))
    return {
        "ok": True,
        "source": str(source_path),
        "output": str(output_path),
        "in_place": in_place,
        "source_sha256": source_hash,
        "output_sha256": sha256(output_path),
        "backup": str(backup_path) if backup_path else None,
        "frames": FRAME_COUNT,
    }


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("atlas", type=Path, help="source v2 WebP atlas")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--expected-source-sha256")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.in_place and args.output:
        raise SystemExit("choose --in-place or --output, not both")
    if not args.in_place and not args.output:
        raise SystemExit("use --output, or explicitly choose --in-place")
    output = args.atlas if args.in_place else args.output
    try:
        result = repair_atlas(
            source_path=args.atlas,
            output_path=output,
            expected_source_sha256=args.expected_source_sha256,
            backup_path=args.backup,
            force=args.force,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.json_out:
        write_json_atomic(args.json_out.resolve(), result)
    print(rendered, end="")


if __name__ == "__main__":
    main()
