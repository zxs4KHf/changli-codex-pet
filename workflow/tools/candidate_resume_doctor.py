#!/usr/bin/env python3
"""Audit a hatch-pet v2 candidate checkpoint without changing its files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

EXPECTED_JOBS = (
    "base",
    "idle",
    "running-right",
    "running-left",
    "waving",
    "jumping",
    "failed",
    "waiting",
    "running",
    "review",
    "look-cardinals",
    "look-row-9",
    "look-row-10",
)
STANDARD_JOBS = EXPECTED_JOBS[1:10]
EXPECTED_DEPENDENCIES = {
    "base": (),
    "idle": ("base",),
    "running-right": ("base",),
    "running-left": ("base", "running-right"),
    "waving": ("base",),
    "jumping": ("base",),
    "failed": ("base",),
    "waiting": ("base",),
    "running": ("base",),
    "review": ("base",),
    "look-cardinals": tuple(EXPECTED_JOBS[1:10]),
    "look-row-9": ("look-cardinals",),
    "look-row-10": ("look-cardinals", "look-row-9"),
}
STANDARD_OUTPUT_SIZES = {
    "base": (192, 208),
    "idle": (1152, 208),
    "running-right": (1536, 208),
    "running-left": (1536, 208),
    "waving": (768, 208),
    "jumping": (960, 208),
    "failed": (1536, 208),
    "waiting": (1152, 208),
    "running": (1152, 208),
    "review": (1152, 208),
}
CARDINALS = ("000", "090", "180", "270")
CARDINAL_EXPECTED = {
    "000": "up",
    "090": "screen-right",
    "180": "down",
    "270": "screen-left",
}
ROW9_DIRECTIONS = (
    ("000", "up"),
    ("022.5", "up-right"),
    ("045", "up-right"),
    ("067.5", "up-right"),
    ("090", "right"),
    ("112.5", "down-right"),
    ("135", "down-right"),
    ("157.5", "down-right"),
)
ALLOWED_STATUSES = {"pending", "complete"}
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
STANDARD_ATLAS_SIZE = (1536, 1872)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"could not read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def resolve_path(run_dir: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    return path.resolve() if path.is_absolute() else (run_dir / path).resolve()


def relative_label(run_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(run_dir).as_posix()
    except ValueError:
        return str(path)


def is_within(root: Path, path: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def image_artifact(run_dir: Path, raw: str, errors: list[str]) -> dict[str, Any] | None:
    path = resolve_path(run_dir, raw)
    if not path.is_file():
        errors.append(f"missing required artifact: {raw}")
        return None
    try:
        with Image.open(path) as image:
            width, height = image.size
            format_name = image.format
            mode = image.mode
            frames = getattr(image, "n_frames", 1)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"could not open image artifact {raw}: {exc}")
        return None
    return {
        "path": relative_label(run_dir, path),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "format": format_name,
        "mode": mode,
        "width": width,
        "height": height,
        "frames": frames,
    }


def find_cycle(jobs: dict[str, dict[str, Any]]) -> list[str] | None:
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(job_id: str) -> list[str] | None:
        if job_id in visiting:
            start = visiting.index(job_id)
            return visiting[start:] + [job_id]
        if job_id in visited:
            return None
        visiting.append(job_id)
        dependencies = jobs[job_id].get("depends_on", [])
        if not isinstance(dependencies, list):
            dependencies = []
        for dependency in dependencies:
            if not isinstance(dependency, str):
                continue
            if dependency in jobs:
                cycle = visit(dependency)
                if cycle:
                    return cycle
        visiting.pop()
        visited.add(job_id)
        return None

    for job_id in jobs:
        cycle = visit(job_id)
        if cycle:
            return cycle
    return None


def infer_stage(jobs: dict[str, dict[str, Any]]) -> str:
    if any(jobs.get(job_id, {}).get("status") != "complete" for job_id in STANDARD_JOBS):
        return "standard-rows"
    if jobs.get("look-cardinals", {}).get("status") != "complete":
        return "look-cardinals"
    if jobs.get("look-row-9", {}).get("status") != "complete":
        return "look-row-9"
    if jobs.get("look-row-10", {}).get("status") != "complete":
        return "look-row-10"
    return "final-v2-qa"


def audit_candidate(run_dir: Path, max_input_images: int = 5) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    artifacts: list[dict[str, Any]] = []

    request_path = run_dir / "pet_request.json"
    manifest_path = run_dir / "imagegen-jobs.json"
    if not request_path.is_file():
        errors.append("missing pet_request.json")
    if not manifest_path.is_file():
        errors.append("missing imagegen-jobs.json")
    if errors:
        return {
            "schema_version": 1,
            "run_name": run_dir.name,
            "ok": False,
            "stage": "unknown",
            "next_ready_jobs": [],
            "errors": errors,
            "warnings": warnings,
            "artifacts": artifacts,
        }

    try:
        request = load_json(request_path)
        manifest = load_json(manifest_path)
    except ValueError as exc:
        errors.append(str(exc))
        return {
            "schema_version": 1,
            "run_name": run_dir.name,
            "ok": False,
            "stage": "unknown",
            "next_ready_jobs": [],
            "errors": errors,
            "warnings": warnings,
            "artifacts": artifacts,
        }

    atlas_contract = request.get("atlas", {})
    expected_contract = {
        "columns": 8,
        "rows": 11,
        "cell_width": 192,
        "cell_height": 208,
        "width": 1536,
        "height": 2288,
    }
    for key, expected in expected_contract.items():
        if atlas_contract.get(key) != expected:
            errors.append(f"pet_request atlas.{key} must be {expected}, got {atlas_contract.get(key)!r}")
    if request.get("sprite_version_number") != 2:
        errors.append("pet_request sprite_version_number must be 2")
    chroma_key = request.get("chroma_key", {}).get("hex")
    if not isinstance(chroma_key, str) or not HEX_COLOR.fullmatch(chroma_key):
        errors.append("pet_request chroma_key.hex must be #RRGGBB")

    raw_jobs = manifest.get("jobs")
    if not isinstance(raw_jobs, list):
        errors.append("imagegen-jobs.json jobs must be an array")
        raw_jobs = []
    jobs: dict[str, dict[str, Any]] = {}
    for index, job in enumerate(raw_jobs):
        if not isinstance(job, dict):
            errors.append(f"job index {index} must be an object")
            continue
        job_id = job.get("id")
        if not isinstance(job_id, str) or not job_id:
            errors.append(f"job index {index} has invalid id")
            continue
        if job_id in jobs:
            errors.append(f"duplicate job id: {job_id}")
            continue
        jobs[job_id] = job

    missing_jobs = sorted(set(EXPECTED_JOBS) - set(jobs))
    extra_jobs = sorted(set(jobs) - set(EXPECTED_JOBS))
    if missing_jobs:
        errors.append(f"missing required jobs: {', '.join(missing_jobs)}")
    if extra_jobs:
        warnings.append(f"unexpected jobs present: {', '.join(extra_jobs)}")

    for job_id, job in jobs.items():
        status = job.get("status")
        if status not in ALLOWED_STATUSES:
            errors.append(f"job {job_id} has invalid status {status!r}")
        dependencies = job.get("depends_on", [])
        if not isinstance(dependencies, list) or any(not isinstance(value, str) for value in dependencies):
            errors.append(f"job {job_id} depends_on must be a string array")
            dependencies = []
        for dependency in dependencies:
            if dependency not in jobs:
                errors.append(f"job {job_id} depends on unknown job {dependency}")
        if isinstance(dependencies, list) and all(isinstance(value, str) for value in dependencies):
            expected_dependencies = EXPECTED_DEPENDENCIES.get(job_id)
            if expected_dependencies is not None and tuple(dependencies) != expected_dependencies:
                errors.append(
                    f"job {job_id} dependencies must be {list(expected_dependencies)}, got {dependencies}"
                )

        prompt_file = job.get("prompt_file")
        if isinstance(prompt_file, str) and prompt_file:
            resolved_prompt = resolve_path(run_dir, prompt_file)
            if not is_within(run_dir, resolved_prompt):
                errors.append(f"job {job_id} prompt_file escapes the run directory: {prompt_file}")
            elif not resolved_prompt.is_file():
                errors.append(f"job {job_id} is missing prompt_file: {prompt_file}")
        else:
            errors.append(f"job {job_id} is missing prompt_file")

        output_path = job.get("output_path")
        if not isinstance(output_path, str) or not output_path:
            errors.append(f"job {job_id} is missing output_path")
        elif not is_within(run_dir, resolve_path(run_dir, output_path)):
            errors.append(f"job {job_id} output_path escapes the run directory: {output_path}")
        elif status == "complete":
            output_artifact = image_artifact(run_dir, output_path, errors)
            expected_size = STANDARD_OUTPUT_SIZES.get(job_id)
            if output_artifact and expected_size:
                if (output_artifact["width"], output_artifact["height"]) != expected_size:
                    errors.append(
                        f"complete job {job_id} output must be {expected_size[0]}x{expected_size[1]}"
                    )
                if output_artifact["format"] != "PNG" or "A" not in str(output_artifact["mode"]):
                    errors.append(f"complete job {job_id} output must be an RGBA PNG")

        inputs = job.get("input_images", [])
        if not isinstance(inputs, list):
            errors.append(f"job {job_id} input_images must be an array")
            inputs = []
        if status != "complete" and len(inputs) > max_input_images:
            errors.append(
                f"pending job {job_id} has {len(inputs)} input images; current limit is {max_input_images}"
            )
        elif len(inputs) > max_input_images:
            warnings.append(
                f"historical complete job {job_id} has {len(inputs)} input images; current limit is {max_input_images}"
            )
        ready = status != "complete" and all(
            jobs.get(dependency, {}).get("status") == "complete" for dependency in dependencies
        )
        pending_dependency_outputs = {
            resolve_path(run_dir, jobs[dependency]["output_path"])
            for dependency in dependencies
            if dependency in jobs
            and jobs[dependency].get("status") != "complete"
            and isinstance(jobs[dependency].get("output_path"), str)
        }
        for item in inputs:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                errors.append(f"job {job_id} has an invalid input image entry")
                continue
            if not isinstance(item.get("role"), str) or not item["role"].strip():
                errors.append(f"job {job_id} input {item['path']} is missing a role")
            path = resolve_path(run_dir, item["path"])
            if not is_within(run_dir, path):
                errors.append(f"job {job_id} input escapes the run directory: {item['path']}")
            elif ready and not path.is_file():
                errors.append(f"ready job {job_id} is missing input image: {item['path']}")
            elif not path.is_file() and path not in pending_dependency_outputs:
                warnings.append(f"job {job_id} input is not currently available: {item['path']}")

    cycle = find_cycle(jobs)
    if cycle:
        errors.append(f"job dependency cycle: {' -> '.join(cycle)}")

    complete_jobs = {job_id for job_id, job in jobs.items() if job.get("status") == "complete"}
    next_ready_jobs: list[str] = []
    for job_id, job in jobs.items():
        dependencies = job.get("depends_on", [])
        if (
            job.get("status") != "complete"
            and isinstance(dependencies, list)
            and all(isinstance(dependency, str) and dependency in complete_jobs for dependency in dependencies)
        ):
            next_ready_jobs.append(job_id)
    next_ready_jobs.sort()
    stage = infer_stage(jobs)

    if jobs.get("look-row-9", {}).get("status") == "complete":
        row9_gate_error_count = len(errors)
        registered = image_artifact(run_dir, "qa/look-row-9-registered.png", errors)
        if registered and (
            (registered["width"], registered["height"]) != (1536, 208)
            or registered["format"] != "PNG"
            or "A" not in str(registered["mode"])
        ):
            errors.append("completed look-row-9 requires a 1536x208 RGBA registered row")
        try:
            registration = load_json(run_dir / "qa" / "look-row-9-registration.json")
            scale = registration.get("scale")
            if not isinstance(scale, (int, float)) or isinstance(scale, bool) or scale <= 0:
                errors.append("qa/look-row-9-registration.json failed")
        except ValueError as exc:
            errors.append(str(exc))
        for filename in ("look-row-9-edge.json", "look-row-9-continuity.json"):
            try:
                gate = load_json(run_dir / "qa" / filename)
                if gate.get("ok") is not True or gate.get("errors"):
                    errors.append(f"qa/{filename} failed")
            except ValueError as exc:
                errors.append(str(exc))
        try:
            semantics = load_json(run_dir / "qa" / "look-row-9-semantics.json")
            directions = semantics.get("directions", [])
            observed = tuple(
                (item.get("direction"), item.get("expected"))
                for item in directions
                if isinstance(item, dict)
            )
            if semantics.get("ok") is not True or observed != ROW9_DIRECTIONS:
                errors.append("qa/look-row-9-semantics.json must pass the fixed row-9 direction order")
            for item in directions:
                if not isinstance(item, dict):
                    continue
                if item.get("verdict") not in {"pass", "warning"}:
                    errors.append(f"row-9 direction {item.get('direction')} has a hard semantic failure")
                if not str(item.get("observed", "")).strip() or not str(item.get("reason", "")).strip():
                    errors.append(f"row-9 direction {item.get('direction')} lacks semantic evidence")
        except ValueError as exc:
            errors.append(str(exc))
        if len(errors) > row9_gate_error_count and "look-row-10" in next_ready_jobs:
            next_ready_jobs.remove("look-row-10")

    resume_inputs: list[dict[str, Any]] = []
    for job_id in next_ready_jobs:
        job = jobs[job_id]
        prompt_file = job.get("prompt_file")
        prompt_path = resolve_path(run_dir, prompt_file) if isinstance(prompt_file, str) else None
        if prompt_path is not None and prompt_path.is_file():
            resume_inputs.append(
                {
                    "job": job_id,
                    "role": "prompt",
                    "path": relative_label(run_dir, prompt_path),
                    "sha256": sha256(prompt_path),
                    "bytes": prompt_path.stat().st_size,
                }
            )
        for item in job.get("input_images", []):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                continue
            input_path = resolve_path(run_dir, item["path"])
            if not input_path.is_file():
                continue
            record = image_artifact(run_dir, item["path"], errors)
            if record:
                record["job"] = job_id
                record["role"] = item.get("role")
                resume_inputs.append(record)

    review_path = run_dir / "qa" / "review.json"
    try:
        review = load_json(review_path)
        if review.get("ok") is not True or review.get("errors"):
            errors.append("qa/review.json standard-row gate failed")
        if review.get("warnings"):
            warnings.append("qa/review.json contains warnings that require visual review")
    except ValueError as exc:
        errors.append(str(exc))
    except FileNotFoundError:
        errors.append("missing qa/review.json")

    standard_atlas = image_artifact(run_dir, "final/spritesheet.webp", errors)
    if standard_atlas:
        artifacts.append(standard_atlas)
        if (standard_atlas["width"], standard_atlas["height"]) != STANDARD_ATLAS_SIZE:
            errors.append(
                "intermediate standard atlas must be 1536x1872 before Look assembly, got "
                f"{standard_atlas['width']}x{standard_atlas['height']}"
            )
        if "A" not in str(standard_atlas["mode"]):
            errors.append("intermediate standard atlas must retain alpha")

    contact_sheet = image_artifact(run_dir, "qa/contact-sheet.png", errors)
    if contact_sheet:
        artifacts.append(contact_sheet)

    if jobs.get("look-cardinals", {}).get("status") == "complete":
        anchors_path = run_dir / "qa" / "cardinal-anchors.json"
        semantics_path = run_dir / "qa" / "cardinal-semantics.json"
        try:
            anchors = load_json(anchors_path)
            if anchors.get("ok") is not True or anchors.get("errors"):
                errors.append("qa/cardinal-anchors.json failed")
            if tuple(anchors.get("directions", [])) != CARDINALS:
                errors.append("qa/cardinal-anchors.json directions must be 000, 090, 180, 270")
        except (ValueError, FileNotFoundError) as exc:
            errors.append(f"could not validate cardinal anchors: {exc}")
        try:
            semantics = load_json(semantics_path)
            directions = semantics.get("directions", [])
            observed = tuple(item.get("direction") for item in directions if isinstance(item, dict))
            if semantics.get("ok") is not True or observed != CARDINALS:
                errors.append("qa/cardinal-semantics.json must pass all four directions in fixed order")
            for item in directions:
                direction = item.get("direction")
                if item.get("expected") != CARDINAL_EXPECTED.get(direction):
                    errors.append(f"cardinal {direction} has the wrong expected label")
                if item.get("verdict") != "pass" or not str(item.get("evidence", "")).strip():
                    errors.append(f"cardinal {direction} lacks a passing evidence-backed verdict")
        except (ValueError, FileNotFoundError) as exc:
            errors.append(f"could not validate cardinal semantics: {exc}")
        approved = image_artifact(run_dir, "decoded/look-anchors-approved.png", errors)
        if approved:
            artifacts.append(approved)
            if (approved["width"], approved["height"]) != (768, 208):
                errors.append("approved cardinal strip must be 768x208")

    resume_hint = {
        "standard-rows": "finish and approve every standard row before Look generation",
        "look-cardinals": "generate and approve 000/090/180/270 as one cardinal family",
        "look-row-9": "generate one coherent row 9, then register and edge-check it immediately",
        "look-row-10": "generate row 10 only from approved cardinals and completed row 9",
        "final-v2-qa": "assemble v2, despill exactly once, validate, blind-test, and visually QA",
    }[stage]

    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_name": run_dir.name,
        "ok": not errors,
        "stage": stage,
        "next_ready_jobs": next_ready_jobs,
        "resume_hint": resume_hint,
        "chroma_key": chroma_key,
        "job_status": {job_id: jobs[job_id].get("status") for job_id in EXPECTED_JOBS if job_id in jobs},
        "resume_inputs": resume_inputs,
        "doctor_sha256": sha256(Path(__file__).resolve()),
        "errors": errors,
        "warnings": warnings,
        "artifacts": artifacts,
    }


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--expect-next", action="append", default=[])
    parser.add_argument("--max-input-images", type=int, default=5)
    args = parser.parse_args()

    result = audit_candidate(args.run_dir, max_input_images=args.max_input_images)
    if args.expect_next:
        expected = sorted(args.expect_next)
        if result["next_ready_jobs"] != expected:
            result["errors"].append(
                f"next ready jobs mismatch: expected {expected}, got {result['next_ready_jobs']}"
            )
            result["ok"] = False
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.json_out:
        write_atomic(args.json_out.expanduser().resolve(), rendered)
    sys.stdout.write(rendered)
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
