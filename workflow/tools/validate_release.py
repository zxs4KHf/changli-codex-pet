#!/usr/bin/env python3
"""Validate the public Changli Codex pet release and its retained QA evidence."""

from __future__ import annotations

import argparse
from collections import Counter
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
EXPECTED_PREVIEW_FRAMES = {
    "idle.gif": 6,
    "running-right.gif": 8,
    "running-left.gif": 8,
    "waving.gif": 4,
    "jumping.gif": 5,
    "failed.gif": 8,
    "waiting.gif": 6,
    "running.gif": 6,
    "review.gif": 6,
}
EXPECTED_DIRECTIONS = (
    ("000", "up"),
    ("022.5", "up-right"),
    ("045", "up-right"),
    ("067.5", "up-right"),
    ("090", "right"),
    ("112.5", "down-right"),
    ("135", "down-right"),
    ("157.5", "down-right"),
    ("180", "down"),
    ("202.5", "down-left"),
    ("225", "down-left"),
    ("247.5", "down-left"),
    ("270", "left"),
    ("292.5", "up-left"),
    ("315", "up-left"),
    ("337.5", "up-left"),
)
EXPECTED_BLIND_PAIRS = (
    ("horizontal-1", "horizontal", "review", "022.5", "screen-right", "337.5", "screen-left"),
    ("horizontal-2", "horizontal", "review", "045", "screen-right", "315", "screen-left"),
    ("horizontal-3", "horizontal", "review", "067.5", "screen-right", "292.5", "screen-left"),
    ("horizontal-4", "horizontal", "hard", "270", "screen-left", "090", "screen-right"),
    ("horizontal-5", "horizontal", "review", "247.5", "screen-left", "112.5", "screen-right"),
    ("horizontal-6", "horizontal", "review", "225", "screen-left", "135", "screen-right"),
    ("horizontal-7", "horizontal", "review", "202.5", "screen-left", "157.5", "screen-right"),
    ("vertical-1", "vertical", "hard", "000", "up", "180", "down"),
    ("vertical-2", "vertical", "review", "022.5", "up", "157.5", "down"),
    ("vertical-3", "vertical", "review", "045", "up", "135", "down"),
    ("vertical-4", "vertical", "review", "112.5", "down", "067.5", "up"),
    ("vertical-5", "vertical", "review", "337.5", "up", "202.5", "down"),
    ("vertical-6", "vertical", "review", "315", "up", "225", "down"),
    ("vertical-7", "vertical", "review", "292.5", "up", "247.5", "down"),
)
EXPECTED_EVIDENCE_FILES = {
    "docs/images/contact-sheet.png",
    "docs/images/look-directions.png",
    "workflow/qa/direction-blind-pairs.png",
    "workflow/qa/installed-contact-sheet.png",
    "workflow/qa/running-rows-installed.png",
    *(f"workflow/qa/previews/{name}" for name in EXPECTED_PREVIEWS),
}


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


def parse_hex_color(value: object) -> tuple[int, int, int] | None:
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        return None
    try:
        return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))
    except ValueError:
        return None


def chroma_fringe_count(image: Image.Image, chroma_key: tuple[int, int, int]) -> int:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    alpha_values = list(alpha.get_flattened_data())
    transparent = Image.new("L", alpha.size)
    transparent.putdata([255 if value == 0 else 0 for value in alpha_values])
    expanded = transparent.filter(ImageFilter.MaxFilter(5))
    return sum(
        alpha_value >= 16
        and nearby_transparency > 0
        and color_distance(color[:3], chroma_key) <= 96
        for color, alpha_value, nearby_transparency in zip(
            rgba.get_flattened_data(),
            alpha_values,
            expanded.get_flattened_data(),
        )
    )


def strict_majority(values: list[str]) -> tuple[str | None, dict[str, int]]:
    counts = Counter(values)
    if not counts:
        return None, {}
    winner, count = counts.most_common(1)[0]
    if count < 2:
        return None, dict(counts)
    return winner, dict(counts)


def validate_direction_semantics(qa_dir: Path, errors: list[str]) -> None:
    path = qa_dir / "direction-semantics.json"
    try:
        directions = load_json(path).get("directions", [])
    except ValueError as exc:
        errors.append(str(exc))
        return
    if not isinstance(directions, list):
        errors.append("direction-semantics.json directions must be an array")
        return
    observed = tuple(
        (item.get("direction"), item.get("expected")) if isinstance(item, dict) else (None, None)
        for item in directions
    )
    if observed != EXPECTED_DIRECTIONS:
        errors.append("direction-semantics.json must contain the fixed 16-direction order and labels")
    allowed_verdicts = {"pass", "warning", "fail"}
    for index, item in enumerate(directions):
        if not isinstance(item, dict):
            errors.append(f"direction semantic item {index} must be an object")
            continue
        direction = item.get("direction")
        if item.get("verdict") not in allowed_verdicts:
            errors.append(f"direction {direction} has invalid verdict {item.get('verdict')!r}")
        if item.get("verdict") == "fail":
            errors.append(f"direction semantic failure: {direction}")
        for field in ("observed", "reason"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"direction {direction} is missing non-empty {field}")


def validate_blind_evidence(qa_dir: Path, release_hash: str, errors: list[str]) -> None:
    names = [
        "direction-blind-answer-key.json",
        "direction-blind-verdicts-1.json",
        "direction-blind-verdicts-2.json",
        "direction-blind-verdicts-3.json",
        "direction-blind-verdicts.json",
        "direction-blind-validation.json",
    ]
    values: dict[str, dict] = {}
    for name in names:
        try:
            values[name] = load_json(qa_dir / name)
        except ValueError as exc:
            errors.append(str(exc))
            return

    answer = values[names[0]]
    if str(answer.get("atlas_sha256", "")).upper() != release_hash:
        errors.append("blind answer key atlas_sha256 does not match the release atlas")
    answer_pairs = answer.get("pairs", [])
    pair_ids = [item.get("pair") for item in answer_pairs if isinstance(item, dict)]
    if len(pair_ids) != 14 or len(set(pair_ids)) != 14:
        errors.append("blind answer key must contain 14 unique pairs")
        return
    answer_by_id = {item["pair"]: item for item in answer_pairs}
    canonical_pairs = []
    for pair_id, axis, gate, a_source, a_expected, b_source, b_expected in EXPECTED_BLIND_PAIRS:
        canonical_pairs.append(
            (
                pair_id,
                axis,
                gate,
                a_source,
                a_expected,
                b_source,
                b_expected,
            )
        )
    observed_pairs = [
        (
            item.get("pair"),
            item.get("axis"),
            item.get("gate"),
            item.get("A", {}).get("source_direction"),
            item.get("A", {}).get("expected_direction"),
            item.get("B", {}).get("source_direction"),
            item.get("B", {}).get("expected_direction"),
        )
        for item in answer_pairs
    ]
    if observed_pairs != canonical_pairs:
        errors.append("blind answer key does not match the fixed pair/axis/gate/direction contract")

    raw_by_file: list[dict[str, dict]] = []
    for name in names[1:4]:
        pairs = values[name].get("pairs", [])
        ids = [item.get("pair") for item in pairs if isinstance(item, dict)]
        if ids != pair_ids:
            errors.append(f"{name} pair order does not match the answer key")
            return
        raw_by_file.append({item["pair"]: item for item in pairs})

    consensus_pairs = values[names[4]].get("pairs", [])
    consensus_ids = [item.get("pair") for item in consensus_pairs if isinstance(item, dict)]
    if consensus_ids != pair_ids:
        errors.append("direction-blind-verdicts.json pair order does not match the answer key")
        return
    consensus_by_id = {item["pair"]: item for item in consensus_pairs}

    for pair_id in pair_ids:
        consensus = consensus_by_id[pair_id]
        for side in ("A", "B"):
            votes = [review[pair_id].get(side) for review in raw_by_file]
            if any(not isinstance(vote, str) for vote in votes):
                errors.append(f"blind pair {pair_id} {side} contains an invalid raw vote")
                continue
            majority, counts = strict_majority(votes)
            if majority is None:
                errors.append(f"blind pair {pair_id} {side} has no strict majority")
                continue
            if consensus.get(side) != majority:
                errors.append(f"blind consensus mismatch for {pair_id} {side}")
            if consensus.get("votes", {}).get(side) != counts:
                errors.append(f"blind vote counts mismatch for {pair_id} {side}")

    validation = values[names[5]]
    validation_pairs = validation.get("pairs", [])
    validation_ids = [item.get("pair") for item in validation_pairs if isinstance(item, dict)]
    if validation_ids != pair_ids:
        errors.append("direction-blind-validation.json pair order does not match the answer key")
        return
    computed_review_required = False
    computed_review_failures: list[str] = []
    for item in validation_pairs:
        pair_id = item["pair"]
        key_item = answer_by_id[pair_id]
        consensus = consensus_by_id[pair_id]
        if item.get("axis") != key_item.get("axis") or item.get("gate") != key_item.get("gate"):
            errors.append(f"blind validation metadata mismatch for {pair_id}")
        for side in ("A", "B"):
            expected = key_item[side]["expected_direction"]
            observed = consensus[side]
            validation_side = item.get(side, {})
            if validation_side.get("expected") != expected or validation_side.get("observed") != observed:
                errors.append(f"blind validation result mismatch for {pair_id} {side}")
            should_pass = observed == expected
            if validation_side.get("pass") is not should_pass:
                errors.append(f"blind validation pass flag mismatch for {pair_id} {side}")
            if key_item.get("gate") == "hard" and not should_pass:
                errors.append(f"blind cardinal hard gate failed for {pair_id} {side}")
            if key_item.get("gate") == "review" and not should_pass:
                computed_review_required = True
                computed_review_failures.append(f"{pair_id}:{side}")
    if validation.get("ok") is not True:
        errors.append("direction-blind-validation.json ok must be true")
    if validation.get("reviewRequired") is not computed_review_required:
        errors.append("blind validation reviewRequired flag does not match recomputed review results")
    if computed_review_required:
        try:
            resolution = load_json(qa_dir / "blind-review-resolution.json")
        except ValueError as exc:
            errors.append(str(exc))
            return
        if resolution.get("decision") != "accept" or resolution.get("severity") != "minor":
            errors.append("blind review warnings require an accepted minor resolution")
        if str(resolution.get("atlas_sha256", "")).upper() != release_hash:
            errors.append("blind review resolution atlas_sha256 does not match the release atlas")
        if resolution.get("reviewed_failures") != computed_review_failures:
            errors.append("blind review resolution does not match recomputed intermediate failures")
        if not isinstance(resolution.get("reviewed_by"), str) or not resolution["reviewed_by"].strip():
            errors.append("blind review resolution must identify reviewed_by")


def checker(size: tuple[int, int], square: int = 16) -> Image.Image:
    image = Image.new("RGB", size, "#ffffff")
    pixels = image.load()
    for y in range(size[1]):
        for x in range(size[0]):
            if (x // square + y // square) % 2:
                pixels[x, y] = (232, 232, 232)
    return image


def focused_head_cell(cell: Image.Image) -> Image.Image:
    bbox = cell.getbbox()
    if bbox is None:
        return cell
    left, top, right, bottom = bbox
    focus_bottom = top + max(1, int((bottom - top) * 0.52))
    crop = cell.crop((max(0, left - 18), max(0, top - 18), min(192, right + 18), min(208, focus_bottom + 18)))
    focused = Image.new("RGBA", (192, 208), (0, 0, 0, 0))
    crop.thumbnail((192, 208), Image.Resampling.LANCZOS)
    focused.alpha_composite(crop, ((192 - crop.width) // 2, (208 - crop.height) // 2))
    return focused


def validate_derived_sheets(root: Path, atlas: Image.Image, errors: list[str]) -> None:
    try:
        with Image.open(root / "docs" / "images" / "contact-sheet.png") as opened:
            sheet = opened.convert("RGB")
        for row in range(ROWS):
            for column in range(COLUMNS):
                cell = atlas.crop((column * 192, row * 208, (column + 1) * 192, (row + 1) * 208))
                cell = cell.resize((96, 104), Image.Resampling.LANCZOS)
                expected = checker((96, 104))
                expected.paste(cell, (0, 0), cell)
                actual = sheet.crop((column * 96, row * 126 + 22, (column + 1) * 96, row * 126 + 126))
                comparison_box = (1, 18, 95, 103)
                if ImageChops.difference(
                    actual.crop(comparison_box), expected.crop(comparison_box)
                ).getbbox() is not None:
                    errors.append(f"contact sheet is not derived from the release atlas at r{row}c{column}")
                    return
    except Exception as exc:  # noqa: BLE001
        errors.append(f"could not validate derived contact sheet: {exc}")
        return

    try:
        with Image.open(root / "docs" / "images" / "look-directions.png") as opened:
            sheet = opened.convert("RGB")
        cells = [(0, 6, 0, 0)] + [
            (9 + index // 8, index % 8, index % 8, 1 + index // 8) for index in range(16)
        ]
        for source_row, source_column, output_column, output_row in cells:
            cell = atlas.crop((source_column * 192, source_row * 208, (source_column + 1) * 192, (source_row + 1) * 208))
            expected = Image.new("RGB", (192, 208), (242, 242, 242))
            expected.paste(cell, (0, 0), cell)
            y = output_row * 234 + 26
            actual = sheet.crop((output_column * 192, y, (output_column + 1) * 192, y + 208))
            if ImageChops.difference(actual, expected).getbbox() is not None:
                errors.append("look direction sheet is not derived from the release atlas")
                return
        for index in range(16):
            cell = atlas.crop(((index % 8) * 192, (9 + index // 8) * 208, (index % 8 + 1) * 192, (10 + index // 8) * 208))
            focus = focused_head_cell(cell)
            expected = Image.new("RGB", (192, 208), (242, 242, 242))
            expected.paste(focus, (0, 0), focus)
            y = (3 + index // 8) * 234 + 26
            actual = sheet.crop(((index % 8) * 192, y, (index % 8 + 1) * 192, y + 208))
            if ImageChops.difference(actual, expected).getbbox() is not None:
                errors.append("look direction focus sheet is not derived from the release atlas")
                return
    except Exception as exc:  # noqa: BLE001
        errors.append(f"could not validate derived look direction sheet: {exc}")


def validate_visual_evidence(root: Path, qa_dir: Path, atlas: Image.Image, release_hash: str, errors: list[str]) -> None:
    previews_dir = qa_dir / "previews"
    actual = {path.name for path in previews_dir.glob("*.gif")} if previews_dir.is_dir() else set()
    if actual != EXPECTED_PREVIEWS:
        errors.append(
            "preview set mismatch; "
            f"missing={sorted(EXPECTED_PREVIEWS - actual)}, extra={sorted(actual - EXPECTED_PREVIEWS)}"
        )
    for name, expected_frames in EXPECTED_PREVIEW_FRAMES.items():
        path = previews_dir / name
        if not path.is_file():
            continue
        try:
            with Image.open(path) as image:
                if image.format != "GIF" or image.size != (CELL_WIDTH, CELL_HEIGHT):
                    errors.append(f"preview {name} must be a 192x208 GIF")
                if getattr(image, "n_frames", 1) != expected_frames:
                    errors.append(
                        f"preview {name} must contain {expected_frames} frames, "
                        f"got {getattr(image, 'n_frames', 1)}"
                    )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"could not open preview {name}: {exc}")

    expected_images = {
        root / "docs" / "images" / "contact-sheet.png": (768, 1386),
        root / "docs" / "images" / "look-directions.png": (1536, 1170),
    }
    for path, expected_size in expected_images.items():
        if not path.is_file():
            errors.append(f"missing visual evidence: {path.relative_to(root)}")
            continue
        try:
            with Image.open(path) as image:
                if image.format != "PNG" or image.size != expected_size:
                    errors.append(
                        f"visual evidence {path.relative_to(root)} must be PNG {expected_size[0]}x{expected_size[1]}"
                    )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"could not open visual evidence {path.relative_to(root)}: {exc}")
    validate_derived_sheets(root, atlas, errors)

    try:
        evidence = load_json(qa_dir / "release-evidence.json")
        if str(evidence.get("atlas_sha256", "")).upper() != release_hash:
            errors.append("release-evidence.json atlas_sha256 does not match the release atlas")
        files = evidence.get("files", {})
        if set(files) != EXPECTED_EVIDENCE_FILES:
            errors.append("release-evidence.json file set does not match required QA media")
        for relative, expected_hash in files.items():
            path = root / relative
            if not path.is_file() or sha256(path) != expected_hash:
                errors.append(f"release evidence hash mismatch: {relative}")
    except ValueError as exc:
        errors.append(str(exc))


def validate(root: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    pet_dir = root / "pet" / "changli"
    manifest_path = pet_dir / "pet.json"
    atlas_path = pet_dir / "spritesheet.webp"
    checksum_path = pet_dir / "checksums.json"
    request_path = root / "workflow" / "pet_request.json"

    for required in (manifest_path, atlas_path, checksum_path, request_path):
        if not required.is_file():
            errors.append(f"missing required file: {required.relative_to(root)}")

    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    try:
        manifest = load_json(manifest_path)
        checksums = load_json(checksum_path)
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
    if checksums.get("schemaVersion") != 1 or checksums.get("algorithm") != "SHA256":
        errors.append("pet/changli/checksums.json has an unsupported format")
    checksum_files = checksums.get("files", {})
    manifest_hash = sha256(manifest_path)
    if checksum_files.get("pet.json") != manifest_hash:
        errors.append("checksums.json pet.json hash mismatch")

    chroma_hex = request.get("repair", {}).get("chroma_key")
    chroma_key = parse_hex_color(chroma_hex)
    if chroma_key is None:
        errors.append("workflow/pet_request.json repair.chroma_key must be #RRGGBB")
        chroma_key = (0, 255, 0)

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
                fringe = chroma_fringe_count(cell, chroma_key) if used else 0
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
    if checksum_files.get("spritesheet.webp") != release_hash:
        errors.append("checksums.json spritesheet.webp hash mismatch")
    expected_hash = request.get("repair", {}).get("release_sha256")
    if release_hash != expected_hash:
        errors.append(f"release SHA-256 mismatch: expected {expected_hash}, got {release_hash}")

    qa_dir = root / "workflow" / "qa"
    qa_checks = {
        "chroma-despill-extended.json": lambda value: value.get("ok") is True
        and value.get("alpha_preserved") is True,
        "direction-blind-validation.json": lambda value: value.get("ok") is True,
        "final-visual-qa.json": lambda value: value.get("visual_qa") == "pass",
        "look-continuity.json": lambda value: value.get("ok") is True,
        "review.json": lambda value: value.get("ok") is True and not value.get("errors"),
        "run-summary.json": lambda value: value.get("ok") is True
        and value.get("releaseSha256") == release_hash,
        "validation-extended.json": lambda value: value.get("ok") is True
        and value.get("width") == EXPECTED_SIZE[0]
        and value.get("height") == EXPECTED_SIZE[1]
        and value.get("sprite_version_number") == 2
        and not value.get("errors")
        and not value.get("warnings"),
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

    try:
        despill = load_json(qa_dir / "chroma-despill-extended.json")
        if str(despill.get("chroma_key", "")).upper() != str(chroma_hex).upper():
            errors.append("despill chroma key does not match workflow/pet_request.json")
        summary = load_json(qa_dir / "run-summary.json")
        if str(summary.get("despillResult", {}).get("chromaKey", "")).upper() != str(chroma_hex).upper():
            errors.append("run-summary chroma key does not match workflow/pet_request.json")
    except ValueError as exc:
        errors.append(str(exc))

    validate_direction_semantics(qa_dir, errors)
    validate_blind_evidence(qa_dir, release_hash, errors)
    validate_visual_evidence(root, qa_dir, image, release_hash, errors)

    return {
        "ok": not errors,
        "atlas": str(atlas_path.relative_to(root)),
        "sha256": release_hash,
        "format": source_format,
        "mode": source_mode,
        "width": image.width,
        "height": image.height,
        "transparent_rgb_residue_pixels": transparent_residue,
        "chroma_key": chroma_hex,
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
