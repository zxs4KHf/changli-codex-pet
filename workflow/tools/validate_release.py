#!/usr/bin/env python3
"""Validate the public Changli Codex pet release and its retained QA evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps

COLUMNS = 8
ROWS = 11
CELL_WIDTH = 192
CELL_HEIGHT = 208
EXPECTED_SIZE = (COLUMNS * CELL_WIDTH, ROWS * CELL_HEIGHT)
EXPECTED_USED_COLUMNS = {
    0: 7,  # six idle frames plus the v2 neutral frame
    1: 8,
    2: 8,
    3: 4,
    4: 5,
    5: 8,
    6: 6,
    7: 6,
    8: 6,
    9: 8,
    10: 8,
}
EXPECTED_PREVIEWS = {
    "idle.gif",
    "running-right.gif",
    "running-left.gif",
    "waving.gif",
    "jumping.gif",
    "failed.gif",
    "waiting.gif",
    "running.gif",
    "review.gif",
}
CHROMA_KEY = (0, 255, 0)


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"could not read JSON {path}: {exc}") from exc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def alpha_nonzero_count(image: Image.Image) -> int:
    return sum(image.getchannel("A").histogram()[1:])


def transparent_rgb_residue_count(image: Image.Image) -> int:
    count = 0
    data = image.convert("RGBA").tobytes()
    for index in range(0, len(data), 4):
        red, green, blue, alpha = data[index : index + 4]
        if alpha == 0 and (red or green or blue):
            count += 1
    return count


def color_distance(color: tuple[int, int, int], key: tuple[int, int, int]) -> float:
    return math.sqrt(sum((channel - key_channel) ** 2 for channel, key_channel in zip(color, key)))


def chroma_fringe_count(image: Image.Image) -> int:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    alpha_values = list(alpha.get_flattened_data())
    transparent = Image.new("L", alpha.size)
    transparent.putdata([255 if value == 0 else 0 for value in alpha_values])
    expanded = transparent.filter(ImageFilter.MaxFilter(5))
    return sum(
        alpha_value >= 16
        and nearby_transparency > 0
        and color_distance(color[:3], CHROMA_KEY) <= 96
        for color, alpha_value, nearby_transparency in zip(
            rgba.get_flattened_data(),
            alpha_values,
            expanded.get_flattened_data(),
        )
    )


def validate(root: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    pet_dir = root / "pet" / "changli"
    manifest_path = pet_dir / "pet.json"
    atlas_path = pet_dir / "spritesheet.webp"
    request_path = root / "workflow" / "pet_request.json"

    for required in (manifest_path, atlas_path, request_path):
        if not required.is_file():
            errors.append(f"missing required file: {required.relative_to(root)}")

    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    try:
        manifest = load_json(manifest_path)
        request = load_json(request_path)
    except ValueError as exc:
        errors.append(str(exc))
        return {"ok": False, "errors": errors, "warnings": warnings}

    expected_manifest = {
        "id": "changli",
        "displayName": "长离",
        "spriteVersionNumber": 2,
        "spritesheetPath": "spritesheet.webp",
    }
    for key, expected in expected_manifest.items():
        if manifest.get(key) != expected:
            errors.append(f"pet.json {key!r} must be {expected!r}, got {manifest.get(key)!r}")
    if not isinstance(manifest.get("description"), str) or not manifest["description"].strip():
        errors.append("pet.json must contain a non-empty description")

    try:
        with Image.open(atlas_path) as opened:
            source_format = opened.format
            source_mode = opened.mode
            image = opened.convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"could not open spritesheet.webp: {exc}")
        return {"ok": False, "errors": errors, "warnings": warnings}

    if image.size != EXPECTED_SIZE:
        errors.append(f"atlas must be {EXPECTED_SIZE[0]}x{EXPECTED_SIZE[1]}, got {image.width}x{image.height}")
    if source_format != "WEBP":
        errors.append(f"release atlas must be WebP, got {source_format}")
    if "A" not in source_mode:
        errors.append(f"release atlas must have alpha, source mode is {source_mode}")

    cell_summary: list[dict[str, int | bool]] = []
    if image.size == EXPECTED_SIZE:
        for row in range(ROWS):
            for column in range(COLUMNS):
                left = column * CELL_WIDTH
                top = row * CELL_HEIGHT
                cell = image.crop((left, top, left + CELL_WIDTH, top + CELL_HEIGHT))
                nontransparent = alpha_nonzero_count(cell)
                used = column < EXPECTED_USED_COLUMNS[row]
                if used and nontransparent < 50:
                    errors.append(f"used cell r{row}c{column} is empty or too sparse")
                if not used and nontransparent:
                    errors.append(f"unused cell r{row}c{column} contains {nontransparent} visible pixels")
                fringe = chroma_fringe_count(cell) if used else 0
                if fringe:
                    errors.append(f"used cell r{row}c{column} has {fringe} green chroma-edge pixels")
                cell_summary.append(
                    {
                        "row": row,
                        "column": column,
                        "used": used,
                        "nontransparent_pixels": nontransparent,
                        "chroma_fringe_pixels": fringe,
                    }
                )

        for column in range(COLUMNS):
            left = column * CELL_WIDTH
            right_cell = image.crop((left, CELL_HEIGHT, left + CELL_WIDTH, CELL_HEIGHT * 2))
            left_cell = image.crop((left, CELL_HEIGHT * 2, left + CELL_WIDTH, CELL_HEIGHT * 3))
            if ImageChops.difference(right_cell, ImageOps.mirror(left_cell)).getbbox() is not None:
                errors.append(f"running-right r1c{column} is not the exact mirror of running-left r2c{column}")

    transparent_residue = transparent_rgb_residue_count(image)
    if transparent_residue:
        errors.append(f"atlas has {transparent_residue} fully transparent pixels with non-zero RGB")

    release_hash = sha256(atlas_path)
    expected_hash = request.get("repair", {}).get("release_sha256")
    if release_hash != expected_hash:
        errors.append(f"release SHA-256 mismatch: expected {expected_hash}, got {release_hash}")

    qa_dir = root / "workflow" / "qa"
    qa_checks = {
        "chroma-despill-extended.json": lambda value: value.get("ok") is True
        and value.get("alpha_preserved") is True,
        "direction-blind-validation.json": lambda value: value.get("ok") is True,
        "final-visual-qa.json": lambda value: value.get("visual_qa") == "pass",
        "review.json": lambda value: value.get("ok") is True and not value.get("errors"),
        "run-summary.json": lambda value: value.get("ok") is True
        and value.get("releaseSha256") == release_hash,
    }
    for filename, predicate in qa_checks.items():
        path = qa_dir / filename
        if not path.is_file():
            errors.append(f"missing QA evidence: workflow/qa/{filename}")
            continue
        try:
            value = load_json(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not predicate(value):
            errors.append(f"QA gate failed: workflow/qa/{filename}")

    semantics_path = qa_dir / "direction-semantics.json"
    try:
        semantics = load_json(semantics_path).get("directions", [])
        if len(semantics) != 16:
            errors.append(f"direction-semantics.json must contain 16 directions, got {len(semantics)}")
        failed_directions = [item.get("direction") for item in semantics if item.get("verdict") == "fail"]
        if failed_directions:
            errors.append(f"direction semantic failures: {', '.join(map(str, failed_directions))}")
    except ValueError as exc:
        errors.append(str(exc))

    previews_dir = qa_dir / "previews"
    actual_previews = {path.name for path in previews_dir.glob("*.gif")} if previews_dir.is_dir() else set()
    if actual_previews != EXPECTED_PREVIEWS:
        missing = sorted(EXPECTED_PREVIEWS - actual_previews)
        extra = sorted(actual_previews - EXPECTED_PREVIEWS)
        errors.append(f"preview set mismatch; missing={missing}, extra={extra}")

    for evidence in (root / "docs" / "images" / "contact-sheet.png", root / "docs" / "images" / "look-directions.png"):
        if not evidence.is_file() or evidence.stat().st_size == 0:
            errors.append(f"missing visual evidence: {evidence.relative_to(root)}")

    return {
        "ok": not errors,
        "atlas": str(atlas_path.relative_to(root)),
        "sha256": release_hash,
        "format": source_format,
        "mode": source_mode,
        "width": image.width,
        "height": image.height,
        "transparent_rgb_residue_pixels": transparent_residue,
        "running_rows_exact_mirrors": not any("running-right" in item for item in errors),
        "used_cells": sum(1 for item in cell_summary if item["used"]),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    result = validate(args.root.resolve())
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.json_out:
        args.json_out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
