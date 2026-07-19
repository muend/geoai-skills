#!/usr/bin/env python3
"""Validate all skill eval files against the versioned repository schema."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
SCHEMA_PATH = ROOT / "evals" / "schema.json"
RUN_SCHEMA_PATH = ROOT / "evals" / "run-schema.json"


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

    skill_folders = sorted(path for path in SKILLS.iterdir() if path.is_dir())
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
        ids = [case.get("id") for case in cases if isinstance(case, dict)] if isinstance(cases, list) else []
        duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
        if duplicates:
            errors.append(f"{relative(eval_path)}: duplicate case ids: {', '.join(duplicates)}")

        for case in cases if isinstance(cases, list) else []:
            if not isinstance(case, dict):
                continue
            if case.get("should_trigger") is False and not case.get("expected_route"):
                errors.append(
                    f"{relative(eval_path)}:{case.get('id', '<unknown>')}: "
                    "negative routing cases require expected_route"
                )

    for error in errors:
        print(f"ERROR {error}")
    print(
        f"\n{len(skill_folders)} eval files checked — "
        f"{case_count} cases, {len(errors)} errors"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
