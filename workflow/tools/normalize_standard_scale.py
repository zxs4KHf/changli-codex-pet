#!/usr/bin/env python3
"""Normalize standard-row frame scale with safe, auditable output behavior."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from uuid import uuid4

from PIL import Image

CELL_WIDTH = 192
CELL_HEIGHT = 208


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def normalize_image(image: Image.Image, target_height: int, baseline: int) -> tuple[Image.Image, dict]:
    rgba = image.convert("RGBA")
    if rgba.size != (CELL_WIDTH, CELL_HEIGHT):
        raise ValueError(f"frame must be {CELL_WIDTH}x{CELL_HEIGHT}, got {rgba.size}")
    bbox = rgba.getbbox()
    if bbox is None:
        raise ValueError("frame is empty")
    if target_height <= 0 or target_height > CELL_HEIGHT:
        raise ValueError(f"target_height must be within 1..{CELL_HEIGHT}")
    if baseline < target_height or baseline > CELL_HEIGHT:
        raise ValueError("baseline must keep the normalized sprite inside the cell")

    sprite = rgba.crop(bbox)
    scale = target_height / sprite.height
    width = max(1, round(sprite.width * scale))
    if width > CELL_WIDTH:
        raise ValueError(
            f"normalized sprite would be {width}px wide, exceeding the {CELL_WIDTH}px cell"
        )
    resized = sprite.resize((width, target_height), Image.Resampling.LANCZOS)
    output = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    left = round((CELL_WIDTH - width) / 2)
    top = baseline - target_height
    output.alpha_composite(resized, (left, top))
    after_bbox = output.getbbox()
    if after_bbox is None or after_bbox[0] < 0 or after_bbox[1] < 0 or after_bbox[2] > CELL_WIDTH or after_bbox[3] > CELL_HEIGHT:
        raise ValueError("normalized frame exceeds the target cell")
    return output, {
        "before_bbox": list(bbox),
        "after_bbox": list(after_bbox),
        "scale": scale,
    }


def save_png_atomic(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    image.save(temporary, format="PNG")
    temporary.replace(path)


def copy_immutable_backup(source: Path, backup: Path) -> None:
    backup.parent.mkdir(parents=True, exist_ok=True)
    if backup.exists():
        if sha256(source) != sha256(backup):
            raise ValueError(f"immutable backup already exists and differs: {backup}")
        return
    shutil.copy2(source, backup)


def normalize_frames(
    frames_root: Path,
    states: list[str],
    target_height: int,
    baseline: int,
    output_root: Path | None,
    in_place: bool,
    backup_root: Path | None,
    force: bool,
) -> list[dict]:
    frames_root = frames_root.resolve()
    if in_place:
        if backup_root is None:
            raise ValueError("--backup-root is required with --in-place")
        resolved_backup_root = backup_root.resolve()
        if resolved_backup_root == frames_root or frames_root in resolved_backup_root.parents:
            raise ValueError("--backup-root must be outside --frames-root")
    else:
        if output_root is None:
            raise ValueError("use --output-root, or explicitly choose --in-place")
        resolved_output_root = output_root.resolve()
        if resolved_output_root == frames_root:
            raise ValueError("--output-root must differ from --frames-root")
        if resolved_output_root.exists() and not resolved_output_root.is_dir():
            raise ValueError(f"output root must be a directory: {resolved_output_root}")
        if resolved_output_root.exists() and not force:
            raise ValueError(f"output root already exists; pass --force to replace it: {resolved_output_root}")

    plans: list[dict] = []
    for state in states:
        source_dir = frames_root / state
        frames = sorted(source_dir.glob("*.png"))
        if not frames:
            raise ValueError(f"state has no PNG frames: {state}")
        for source in frames:
            with Image.open(source) as opened:
                normalized, geometry = normalize_image(opened, target_height, baseline)
            plans.append(
                {
                    "state": state,
                    "source_path": source,
                    "relative_path": Path(state) / source.name,
                    "image": normalized,
                    "before_sha256": sha256(source),
                    "geometry": geometry,
                }
            )

    records: list[dict] = []
    if in_place:
        for plan in plans:
            copy_immutable_backup(
                plan["source_path"], resolved_backup_root / plan["relative_path"]
            )
        try:
            for plan in plans:
                destination = plan["source_path"]
                save_png_atomic(plan["image"], destination)
                records.append(
                    {
                        "state": plan["state"],
                        "source": str(plan["source_path"]),
                        "output": str(destination),
                        "before_sha256": plan["before_sha256"],
                        "after_sha256": sha256(destination),
                        **plan["geometry"],
                    }
                )
        except Exception:
            for plan in plans:
                backup = resolved_backup_root / plan["relative_path"]
                if backup.is_file():
                    shutil.copy2(backup, plan["source_path"])
            raise
    else:
        staging = resolved_output_root.parent / f".{resolved_output_root.name}.staging-{uuid4().hex}"
        rollback = resolved_output_root.parent / f".{resolved_output_root.name}.rollback-{uuid4().hex}"
        old_moved = False
        new_installed = False
        try:
            for plan in plans:
                save_png_atomic(plan["image"], staging / plan["relative_path"])
            if resolved_output_root.exists():
                resolved_output_root.replace(rollback)
                old_moved = True
            staging.replace(resolved_output_root)
            new_installed = True
            for plan in plans:
                destination = resolved_output_root / plan["relative_path"]
                records.append(
                    {
                        "state": plan["state"],
                        "source": str(plan["source_path"]),
                        "output": str(destination),
                        "before_sha256": plan["before_sha256"],
                        "after_sha256": sha256(destination),
                        **plan["geometry"],
                    }
                )
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            if new_installed and resolved_output_root.exists():
                shutil.rmtree(resolved_output_root)
            if old_moved and rollback.exists():
                rollback.replace(resolved_output_root)
            raise
        if old_moved:
            shutil.rmtree(rollback)
    return records


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--states", default="idle,running")
    parser.add_argument("--target-height", type=int, default=158)
    parser.add_argument("--baseline", type=int, default=183)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    states = [value.strip() for value in args.states.split(",") if value.strip()]
    if not states:
        raise SystemExit("--states must contain at least one state")
    try:
        records = normalize_frames(
            frames_root=args.frames_root,
            states=states,
            target_height=args.target_height,
            baseline=args.baseline,
            output_root=args.output_root,
            in_place=args.in_place,
            backup_root=args.backup_root,
            force=args.force,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    write_json_atomic(
        args.json_out.resolve(),
        {
            "ok": True,
            "mode": "in-place" if args.in_place else "new-output",
            "states": states,
            "target_height": args.target_height,
            "baseline": args.baseline,
            "frames": records,
        },
    )


if __name__ == "__main__":
    main()
