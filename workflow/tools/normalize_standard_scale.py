from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image


def normalize_frame(path: Path, target_height: int, baseline: int) -> dict:
    image = Image.open(path).convert("RGBA")
    bbox = image.getbbox()
    if bbox is None:
        raise ValueError(f"empty frame: {path}")

    sprite = image.crop(bbox)
    scale = target_height / sprite.height
    width = max(1, round(sprite.width * scale))
    sprite = sprite.resize((width, target_height), Image.Resampling.LANCZOS)

    output = Image.new("RGBA", image.size, (0, 0, 0, 0))
    left = round((image.width - width) / 2)
    top = baseline - target_height
    output.alpha_composite(sprite, (left, top))
    output.save(path)
    return {
        "frame": str(path),
        "before_bbox": list(bbox),
        "after_bbox": list(output.getbbox() or (0, 0, 0, 0)),
        "scale": scale,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames-root", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--states", default="idle,running")
    parser.add_argument("--target-height", type=int, default=158)
    parser.add_argument("--baseline", type=int, default=183)
    args = parser.parse_args()

    records = []
    for state in [value.strip() for value in args.states.split(",") if value.strip()]:
        source_dir = args.frames_root / state
        backup_dir = args.backup_root / state
        backup_dir.mkdir(parents=True, exist_ok=True)
        for frame in sorted(source_dir.glob("*.png")):
            shutil.copy2(frame, backup_dir / frame.name)
            records.append(normalize_frame(frame, args.target_height, args.baseline))

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(
            {
                "ok": True,
                "states": args.states.split(","),
                "target_height": args.target_height,
                "baseline": args.baseline,
                "frames": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
