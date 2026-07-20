#!/usr/bin/env python3
"""Validate all skill eval files against the versioned repository schema."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
SCHEMA_PATH = ROOT / "evals" / "schema.json"
RUN_SCHEMA_PATH = ROOT / "evals" / "run-schema.json"
MIN_SUITE_CASES = 120
MIN_CASES_PER_SKILL = 7
CATEGORY_MINIMUMS = {
    "positive": 70,
    "negative": 25,
    "ambiguous": 17,
    "collision": 17,
    "artifact-correctness": 17,
}


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    run_schema = json.loads(RUN_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(run_schema)
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    case_count = 0
    category_counts: Counter[str] = Counter()
    critical_skills: set[str] = set()
    behavior_counts: Counter[str] = Counter()

    skill_folders = sorted(path for path in SKILLS.iterdir() if path.is_dir())
    skill_names = {folder.name for folder in skill_folders}
    for folder in skill_folders:
        eval_path = folder / "evals" / "evals.json"
        if not eval_path.exists():
            errors.append(f"{folder.name}: missing {relative(eval_path)}")
            continue
        try:
            data = json.loads(eval_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{relative(eval_path)}: invalid JSON: {exc}")
            continue

        for issue in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
            location = "/".join(str(part) for part in issue.absolute_path) or "<root>"
            errors.append(f"{relative(eval_path)}:{location}: {issue.message}")

        if data.get("skill") != folder.name:
            errors.append(
                f"{relative(eval_path)}: skill '{data.get('skill')}' does not match folder '{folder.name}'"
            )

        cases = data.get("evals", [])
        case_count += len(cases) if isinstance(cases, list) else 0
        if isinstance(cases, list) and len(cases) < MIN_CASES_PER_SKILL:
            errors.append(
                f"{relative(eval_path)}: requires at least {MIN_CASES_PER_SKILL} cases, "
                f"found {len(cases)}"
            )
        ids = [case.get("id") for case in cases if isinstance(case, dict)] if isinstance(cases, list) else []
        duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
        if duplicates:
            errors.append(f"{relative(eval_path)}: duplicate case ids: {', '.join(duplicates)}")

        for case in cases if isinstance(cases, list) else []:
            if not isinstance(case, dict):
                continue
            case_id = case.get("id", "<unknown>")
            case_types = set(case.get("case_types", []))
            category_counts.update(case_types)
            behavior_class = case.get("behavior_class", "routing-only")
            behavior_counts[behavior_class] += 1
            if case.get("critical") is True:
                critical_skills.add(folder.name)
            should_trigger = case.get("should_trigger", True)
            if should_trigger and "positive" not in case_types:
                errors.append(
                    f"{relative(eval_path)}:{case_id}: triggering cases require the positive type"
                )
            if not should_trigger and "negative" not in case_types:
                errors.append(
                    f"{relative(eval_path)}:{case_id}: non-triggering cases require the negative type"
                )
            if "positive" in case_types and "negative" in case_types:
                errors.append(
                    f"{relative(eval_path)}:{case_id}: positive and negative are mutually exclusive"
                )
            if case.get("should_trigger") is False and not case.get("expected_route"):
                errors.append(
                    f"{relative(eval_path)}:{case_id}: "
                    "negative routing cases require expected_route"
                )
            unknown_routes = sorted(set(case.get("expected_route", [])) - skill_names)
            if unknown_routes:
                errors.append(
                    f"{relative(eval_path)}:{case_id}: unknown expected routes: "
                    f"{', '.join(unknown_routes)}"
                )
            if not should_trigger and folder.name in case.get("expected_route", []):
                errors.append(
                    f"{relative(eval_path)}:{case_id}: negative case cannot route to its own skill"
                )
            fixture_paths = [
                fixture.get("workspace_path")
                for fixture in case.get("fixtures", [])
                if isinstance(fixture, dict)
            ]
            if len(fixture_paths) != len(set(fixture_paths)):
                errors.append(
                    f"{relative(eval_path)}:{case_id}: duplicate fixture workspace paths"
                )
            for fixture in case.get("fixtures", []):
                if not isinstance(fixture, dict) or not isinstance(fixture.get("source"), str):
                    continue
                source = (eval_path.parent / fixture["source"]).resolve()
                try:
                    source.relative_to((eval_path.parent / "fixtures").resolve())
                except ValueError:
                    errors.append(
                        f"{relative(eval_path)}:{case_id}: fixture escapes fixture root"
                    )
                    continue
                if not source.is_file():
                    errors.append(
                        f"{relative(eval_path)}:{case_id}: missing fixture {fixture['source']}"
                    )
                if fixture.get("workspace_path") not in case.get("prompt", ""):
                    errors.append(
                        f"{relative(eval_path)}:{case_id}: prompt must name staged fixture "
                        f"{fixture.get('workspace_path')}"
                    )
            artifact_paths = [
                artifact.get("path")
                for artifact in case.get("expected_artifacts", [])
                if isinstance(artifact, dict)
            ]
            if len(artifact_paths) != len(set(artifact_paths)):
                errors.append(
                    f"{relative(eval_path)}:{case_id}: duplicate expected artifact paths"
                )
            overlap = sorted(set(fixture_paths) & set(artifact_paths))
            if overlap:
                errors.append(
                    f"{relative(eval_path)}:{case_id}: fixture/output path overlap: "
                    + ", ".join(overlap)
                )
            if behavior_class == "artifact-producing":
                for artifact_path in artifact_paths:
                    if artifact_path not in case.get("prompt", ""):
                        errors.append(
                            f"{relative(eval_path)}:{case_id}: prompt must name output artifact "
                            f"{artifact_path}"
                        )

    if case_count < MIN_SUITE_CASES:
        errors.append(f"evaluation suite requires at least {MIN_SUITE_CASES} cases, found {case_count}")
    for category, minimum in CATEGORY_MINIMUMS.items():
        if category_counts[category] < minimum:
            errors.append(
                f"evaluation suite requires at least {minimum} '{category}' cases, "
                f"found {category_counts[category]}"
            )
    missing_critical = sorted(skill_names - critical_skills)
    if missing_critical:
        errors.append(
            "every skill requires at least one critical case; missing: "
            + ", ".join(missing_critical)
        )

    for error in errors:
        print(f"ERROR {error}")
    print(
        f"\n{len(skill_folders)} eval files checked — "
        f"{case_count} cases, {len(errors)} errors\n"
        f"Types: "
        + ", ".join(f"{name}={category_counts[name]}" for name in CATEGORY_MINIMUMS)
        + "\nBehavior: "
        + ", ".join(
            f"{name}={behavior_counts[name]}"
            for name in ("routing-only", "advisory", "fixture-backed", "artifact-producing")
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
