from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from workflow.tools.validate_release import validate


class ValidateReleaseEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        repository = Path(__file__).resolve().parents[1]
        shutil.copytree(repository / "pet", self.root / "pet")
        shutil.copytree(repository / "workflow", self.root / "workflow")
        shutil.copytree(repository / "docs" / "images", self.root / "docs" / "images")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def load(self, relative: str) -> dict:
        return json.loads((self.root / relative).read_text(encoding="utf-8"))

    def save(self, relative: str, value: object) -> None:
        (self.root / relative).write_text(json.dumps(value), encoding="utf-8")

    def test_current_release_evidence_passes(self) -> None:
        result = validate(self.root)
        self.assertTrue(result["ok"], result["errors"])

    def test_duplicate_direction_cannot_pass(self) -> None:
        relative = "workflow/qa/direction-semantics.json"
        value = self.load(relative)
        value["directions"][0] = dict(value["directions"][1])
        self.save(relative, value)
        result = validate(self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("fixed 16-direction order" in error for error in result["errors"]))

    def test_corrupt_preview_cannot_pass_as_nonempty_file(self) -> None:
        (self.root / "workflow/qa/previews/idle.gif").write_bytes(b"not a gif")
        result = validate(self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("could not open preview idle.gif" in error for error in result["errors"]))

    def test_same_size_blank_contact_sheet_cannot_pass(self) -> None:
        Image.new("RGB", (768, 1386), "black").save(
            self.root / "docs/images/contact-sheet.png"
        )
        result = validate(self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("contact sheet is not derived" in error for error in result["errors"]))

    def test_blind_answer_key_contract_cannot_be_rewritten(self) -> None:
        relative = "workflow/qa/direction-blind-answer-key.json"
        value = self.load(relative)
        value["pairs"][0]["A"]["source_direction"] = "090"
        self.save(relative, value)
        result = validate(self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("fixed pair/axis/gate/direction contract" in error for error in result["errors"]))

    def test_blind_resolution_is_bound_to_release_atlas(self) -> None:
        relative = "workflow/qa/blind-review-resolution.json"
        value = self.load(relative)
        value["atlas_sha256"] = "0" * 64
        self.save(relative, value)
        result = validate(self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("resolution atlas_sha256" in error for error in result["errors"]))

    def test_tampered_blind_vote_breaks_recomputed_consensus(self) -> None:
        relative = "workflow/qa/direction-blind-verdicts-1.json"
        value = self.load(relative)
        pair = next(item for item in value["pairs"] if item["pair"] == "horizontal-4")
        pair["A"] = "screen-right"
        self.save(relative, value)
        result = validate(self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any(
                "no strict majority" in error or "blind consensus mismatch" in error
                for error in result["errors"]
            )
        )

    def test_review_required_cannot_be_disabled_when_intermediate_votes_fail(self) -> None:
        relative = "workflow/qa/direction-blind-validation.json"
        value = self.load(relative)
        self.assertTrue(any(not item[side]["pass"] for item in value["pairs"] for side in ("A", "B")))
        value["reviewRequired"] = False
        self.save(relative, value)
        result = validate(self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("reviewRequired flag" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
