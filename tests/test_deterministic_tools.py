from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageChops, ImageDraw, ImageOps

from workflow.tools.mirror_running_left_to_right import (
    CELL_HEIGHT,
    CELL_WIDTH,
    FRAME_COUNT,
    RUNNING_LEFT_ROW,
    RUNNING_RIGHT_ROW,
    repair_atlas,
    sha256,
)
from workflow.tools.normalize_standard_scale import normalize_frames


class NormalizeScaleSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.frames = self.root / "frames"
        (self.frames / "running").mkdir(parents=True)
        image = Image.new("RGBA", (192, 208), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((50, 40, 140, 190), fill=(255, 0, 0, 255))
        image.save(self.frames / "running" / "00.png")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_new_output_preserves_source(self) -> None:
        source = self.frames / "running" / "00.png"
        before = sha256(source)
        output = self.root / "normalized"
        records = normalize_frames(
            self.frames, ["running"], 120, 170, output, False, None, False
        )
        self.assertEqual(before, sha256(source))
        self.assertTrue((output / "running" / "00.png").is_file())
        self.assertEqual(records[0]["after_bbox"][3], 170)

    def test_repeated_in_place_run_cannot_overwrite_original_backup(self) -> None:
        backup = self.root / "backup"
        normalize_frames(self.frames, ["running"], 120, 170, None, True, backup, False)
        with self.assertRaisesRegex(ValueError, "immutable backup"):
            normalize_frames(self.frames, ["running"], 100, 160, None, True, backup, False)

    def test_in_place_backup_root_cannot_be_the_source_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "backup-root must be outside"):
            normalize_frames(
                self.frames, ["running"], 120, 170, None, True, self.frames, False
            )

    def test_validation_failure_leaves_no_partial_output(self) -> None:
        bad = Image.new("RGBA", (192, 208), (0, 0, 0, 0))
        ImageDraw.Draw(bad).rectangle((0, 50, 191, 149), fill=(255, 0, 0, 255))
        bad.save(self.frames / "running" / "01.png")
        output = self.root / "out"
        with self.assertRaisesRegex(ValueError, "exceeding"):
            normalize_frames(self.frames, ["running"], 208, 208, output, False, None, False)
        self.assertFalse(output.exists())

    def test_output_root_file_is_rejected(self) -> None:
        output = self.root / "out"
        output.write_text("not a directory", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "output root must be a directory"):
            normalize_frames(self.frames, ["running"], 120, 170, output, False, None, True)

    def test_in_place_write_failure_restores_every_source(self) -> None:
        second = self.frames / "running" / "01.png"
        image = Image.new("RGBA", (192, 208), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((60, 50, 130, 180), fill=(255, 0, 0, 255))
        image.save(second)
        source_paths = sorted((self.frames / "running").glob("*.png"))
        before = {path: sha256(path) for path in source_paths}
        backup = self.root / "backup"
        from workflow.tools import normalize_standard_scale as module

        real_save = module.save_png_atomic
        calls = 0

        def fail_second(image: Image.Image, path: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated write failure")
            real_save(image, path)

        with mock.patch.object(module, "save_png_atomic", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "simulated write failure"):
                normalize_frames(self.frames, ["running"], 120, 170, None, True, backup, False)
        self.assertEqual(before, {path: sha256(path) for path in source_paths})

    def test_width_overflow_is_rejected(self) -> None:
        image = Image.new("RGBA", (192, 208), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((0, 50, 191, 149), fill=(255, 0, 0, 255))
        image.save(self.frames / "running" / "00.png")
        with self.assertRaisesRegex(ValueError, "exceeding"):
            normalize_frames(
                self.frames, ["running"], 208, 208, self.root / "out", False, None, False
            )


class MirrorRepairSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.webp"
        atlas = Image.new("RGBA", (1536, 2288), (0, 0, 0, 0))
        draw = ImageDraw.Draw(atlas)
        for column in range(FRAME_COUNT):
            x = column * CELL_WIDTH
            y = RUNNING_LEFT_ROW * CELL_HEIGHT
            draw.polygon(
                [(x + 30, y + 30), (x + 160, y + 60), (x + 50, y + 180)],
                fill=(255, 20 * column, 0, 255),
            )
        atlas.save(self.source, "WEBP", lossless=True, method=6, exact=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_new_output_is_exact_mirror_and_source_is_unchanged(self) -> None:
        before = sha256(self.source)
        output = self.root / "output.webp"
        result = repair_atlas(self.source, output, expected_source_sha256=before)
        self.assertEqual(before, sha256(self.source))
        self.assertEqual(result["source_sha256"], before)
        with Image.open(output) as opened:
            atlas = opened.convert("RGBA")
        for column in range(FRAME_COUNT):
            x = column * CELL_WIDTH
            left = atlas.crop(
                (x, RUNNING_LEFT_ROW * CELL_HEIGHT, x + CELL_WIDTH, (RUNNING_LEFT_ROW + 1) * CELL_HEIGHT)
            )
            right = atlas.crop(
                (x, RUNNING_RIGHT_ROW * CELL_HEIGHT, x + CELL_WIDTH, (RUNNING_RIGHT_ROW + 1) * CELL_HEIGHT)
            )
            self.assertIsNone(ImageChops.difference(right, ImageOps.mirror(left)).getbbox())

    def test_in_place_requires_backup(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires --backup"):
            repair_atlas(self.source, self.source)

    def test_in_place_backup_cannot_be_the_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "backup must differ"):
            repair_atlas(self.source, self.source, backup_path=self.source)

    def test_wrong_source_hash_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match"):
            repair_atlas(self.source, self.root / "out.webp", expected_source_sha256="0" * 64)


if __name__ == "__main__":
    unittest.main()
