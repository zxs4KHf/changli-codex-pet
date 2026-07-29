from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from workflow.tools.candidate_resume_doctor import (
    CARDINALS,
    EXPECTED_JOBS,
    STANDARD_OUTPUT_SIZES,
    audit_candidate,
)


class CandidateResumeDoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.temporary.name)
        for directory in ("decoded", "final", "prompts", "qa", "references"):
            (self.run_dir / directory).mkdir(parents=True, exist_ok=True)

        request = {
            "sprite_version_number": 2,
            "atlas": {
                "columns": 8,
                "rows": 11,
                "cell_width": 192,
                "cell_height": 208,
                "width": 1536,
                "height": 2288,
            },
            "chroma_key": {"hex": "#0000FF"},
        }
        self.write_json("pet_request.json", request)

        jobs = []
        dependencies = {
            "base": [],
            **{job_id: ["base"] for job_id in EXPECTED_JOBS[1:10]},
            "look-cardinals": list(EXPECTED_JOBS[1:10]),
            "look-row-9": ["look-cardinals"],
            "look-row-10": ["look-cardinals", "look-row-9"],
        }
        dependencies["running-left"] = ["base", "running-right"]
        for job_id in EXPECTED_JOBS:
            status = "complete" if job_id not in {"look-row-9", "look-row-10"} else "pending"
            prompt = f"prompts/{job_id}.md"
            output = f"decoded/{job_id}.png"
            (self.run_dir / prompt).write_text(job_id, encoding="utf-8")
            inputs = []
            if job_id == "look-row-9":
                for index in range(5):
                    path = f"references/row9-{index}.png"
                    self.make_image(path, (8, 8))
                    inputs.append({"path": path, "role": f"reference {index}"})
            jobs.append(
                {
                    "id": job_id,
                    "kind": "test",
                    "status": status,
                    "prompt_file": prompt,
                    "input_images": inputs,
                    "output_path": output,
                    "depends_on": dependencies[job_id],
                }
            )
            if status == "complete":
                self.make_image(output, STANDARD_OUTPUT_SIZES.get(job_id, (16, 16)))
        self.manifest = {"jobs": jobs}
        self.write_json("imagegen-jobs.json", self.manifest)

        self.write_json("qa/review.json", {"ok": True, "errors": [], "warnings": []})
        self.make_image("final/spritesheet.webp", (1536, 1872), format_name="WEBP")
        self.make_image("qa/contact-sheet.png", (64, 64))
        self.write_json(
            "qa/cardinal-anchors.json", {"ok": True, "errors": [], "directions": list(CARDINALS)}
        )
        self.write_json(
            "qa/cardinal-semantics.json",
            {
                "ok": True,
                "directions": [
                    {
                        "direction": direction,
                        "expected": expected,
                        "verdict": "pass",
                        "evidence": "visible landmark",
                    }
                    for direction, expected in zip(
                        CARDINALS, ("up", "screen-right", "down", "screen-left")
                    )
                ],
            },
        )
        self.make_image("decoded/look-anchors-approved.png", (768, 208))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_json(self, relative: str, value: object) -> None:
        path = self.run_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def make_image(self, relative: str, size: tuple[int, int], format_name: str = "PNG") -> None:
        path = self.run_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGBA", size, (0, 0, 0, 0))
        image.putpixel((0, 0), (255, 0, 0, 255))
        image.save(path, format=format_name)

    def job(self, job_id: str) -> dict:
        return next(job for job in self.manifest["jobs"] if job["id"] == job_id)

    def save_manifest(self) -> None:
        self.write_json("imagegen-jobs.json", self.manifest)

    def test_valid_checkpoint_is_ready_for_row_9(self) -> None:
        result = audit_candidate(self.run_dir)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["stage"], "look-row-9")
        self.assertEqual(result["next_ready_jobs"], ["look-row-9"])
        self.assertEqual(len(result["resume_inputs"]), 6)
        self.assertTrue(all(item["sha256"] for item in result["resume_inputs"]))

    def test_ready_job_missing_reference_fails(self) -> None:
        (self.run_dir / "references/row9-3.png").unlink()
        result = audit_candidate(self.run_dir)
        self.assertFalse(result["ok"])
        self.assertTrue(any("missing input image" in error for error in result["errors"]))

    def test_pending_job_over_reference_limit_fails(self) -> None:
        extra = "references/row9-extra.png"
        self.make_image(extra, (8, 8))
        self.job("look-row-9")["input_images"].append({"path": extra, "role": "extra"})
        self.save_manifest()
        result = audit_candidate(self.run_dir)
        self.assertFalse(result["ok"])
        self.assertTrue(any("current limit is 5" in error for error in result["errors"]))

    def test_wrong_cardinal_order_fails(self) -> None:
        value = json.loads((self.run_dir / "qa/cardinal-semantics.json").read_text())
        value["directions"][1], value["directions"][3] = value["directions"][3], value["directions"][1]
        self.write_json("qa/cardinal-semantics.json", value)
        result = audit_candidate(self.run_dir)
        self.assertFalse(result["ok"])
        self.assertTrue(any("fixed order" in error for error in result["errors"]))

    def test_dependency_cycle_fails(self) -> None:
        self.job("base")["depends_on"] = ["look-row-9"]
        self.save_manifest()
        result = audit_candidate(self.run_dir)
        self.assertFalse(result["ok"])
        self.assertTrue(any("dependency cycle" in error for error in result["errors"]))

    def test_noncanonical_look_row_dependency_fails(self) -> None:
        self.job("look-row-10")["depends_on"] = ["look-cardinals"]
        self.save_manifest()
        result = audit_candidate(self.run_dir)
        self.assertFalse(result["ok"])
        self.assertTrue(any("look-row-10 dependencies must be" in error for error in result["errors"]))

    def test_complete_standard_output_has_fixed_geometry(self) -> None:
        self.make_image("decoded/idle.png", (1, 1))
        result = audit_candidate(self.run_dir)
        self.assertFalse(result["ok"])
        self.assertTrue(any("idle output must be 1152x208" in error for error in result["errors"]))

    def test_external_input_is_rejected(self) -> None:
        external = self.run_dir.parent / "external-reference.png"
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(external)
        try:
            self.job("look-row-9")["input_images"][0]["path"] = str(external)
            self.save_manifest()
            result = audit_candidate(self.run_dir)
            self.assertFalse(result["ok"])
            self.assertTrue(any("input escapes the run directory" in error for error in result["errors"]))
        finally:
            external.unlink(missing_ok=True)

    def complete_row_9_registration(self) -> None:
        self.job("look-row-9")["status"] = "complete"
        self.make_image("decoded/look-row-9.png", (1536, 208))
        self.make_image("qa/look-row-9-registered.png", (1536, 208))
        self.write_json("qa/look-row-9-registration.json", {"scale": 1.0})
        self.save_manifest()

    def test_row_10_is_blocked_until_all_row_9_incremental_qa_exists(self) -> None:
        self.complete_row_9_registration()
        result = audit_candidate(self.run_dir)
        self.assertFalse(result["ok"])
        self.assertNotIn("look-row-10", result["next_ready_jobs"])
        self.assertTrue(any("look-row-9-edge.json" in error for error in result["errors"]))

    def test_row_10_becomes_ready_after_all_row_9_incremental_qa_passes(self) -> None:
        self.complete_row_9_registration()
        self.write_json("qa/look-row-9-edge.json", {"ok": True, "errors": []})
        self.write_json("qa/look-row-9-continuity.json", {"ok": True, "errors": []})
        self.write_json(
            "qa/look-row-9-semantics.json",
            {
                "ok": True,
                "directions": [
                    {
                        "direction": direction,
                        "expected": expected,
                        "observed": expected,
                        "reason": "visible landmark",
                        "verdict": "pass",
                    }
                    for direction, expected in (
                        ("000", "up"),
                        ("022.5", "up-right"),
                        ("045", "up-right"),
                        ("067.5", "up-right"),
                        ("090", "right"),
                        ("112.5", "down-right"),
                        ("135", "down-right"),
                        ("157.5", "down-right"),
                    )
                ],
            },
        )
        result = audit_candidate(self.run_dir)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["next_ready_jobs"], ["look-row-10"])

    def test_malformed_dependency_list_reports_error_without_crashing(self) -> None:
        self.job("look-row-9")["depends_on"] = {"look-cardinals": True}
        self.save_manifest()
        result = audit_candidate(self.run_dir)
        self.assertFalse(result["ok"])
        self.assertTrue(any("depends_on must be a string array" in error for error in result["errors"]))

    def test_ready_job_missing_prompt_reports_error_without_crashing(self) -> None:
        del self.job("look-row-9")["prompt_file"]
        self.save_manifest()
        result = audit_candidate(self.run_dir)
        self.assertFalse(result["ok"])
        self.assertTrue(any("missing prompt_file" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
