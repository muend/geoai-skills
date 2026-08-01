"""Render a deterministic, answer-safe prompt for one external case."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from build_external_eval_freeze import EXPECTED_CASE_IDS
from build_external_producer_interface import (
    INTERFACE_ID,
    INTERFACE_ROOT,
    SUITE_ROOT,
    read_json,
    validate_producer_interface,
)
from build_external_producer_interface_v2 import (
    INTERFACE_ID as INTERFACE_V2_ID,
    INTERFACE_ROOT as INTERFACE_V2_ROOT,
    validate_producer_interface_v2,
)

STANDARD_ENVELOPE = (
    "You are executing one public/synthetic external transfer case in an isolated "
    "writable workspace. Local Agent Skills are installed under `.agents/skills`. "
    "Before solving, load and follow every locally installed skill whose trigger "
    "applies. Do not use web search, browsers, connectors, MCP servers, network "
    "tools, or external data. Work only with the local fixture and files in this "
    "workspace. Do not stop at a plan: create every requested artifact under "
    "`outputs/`, run local checks, and then briefly state which skill(s) you loaded "
    "and which files you created. Do not modify the fixture."
)


def _artifact_block(artifact: dict[str, Any]) -> list[str]:
    """Render one artifact without exposing reference analytical values."""
    fields = ", ".join(f"`{field}`" for field in artifact["required_fields"])
    lines = [
        f"### `{artifact['path']}` ({artifact['format']})",
        f"Required fields or markers, in the declared order where applicable: {fields}",
    ]
    lines.extend(f"- {requirement}" for requirement in artifact["requirements"])
    return lines


def _interface_config(
    interface_version: int,
) -> tuple[str, Path, Any]:
    """Return the frozen identity, source root, and validator for one version."""
    if interface_version == 1:
        return INTERFACE_ID, INTERFACE_ROOT, validate_producer_interface
    if interface_version == 2:
        return INTERFACE_V2_ID, INTERFACE_V2_ROOT, validate_producer_interface_v2
    raise ValueError(f"unsupported producer-interface version: {interface_version}")


def render_prompt(
    case_id: str,
    suite_root: Path = SUITE_ROOT,
    interface_version: int = 1,
) -> str:
    """Return the exact producer-interface prompt for one frozen case."""
    if case_id not in EXPECTED_CASE_IDS:
        raise ValueError(f"unknown frozen case_id: {case_id}")
    interface_id, configured_root, interface_validator = _interface_config(
        interface_version
    )
    errors = interface_validator(suite_root)
    if errors:
        raise ValueError("producer interface is invalid: " + "; ".join(errors))

    case = read_json(suite_root / "cases" / case_id / "case.json")
    interface_root = suite_root / configured_root.relative_to(SUITE_ROOT)
    interface = read_json(interface_root / f"{case_id}.json")
    lines = [
        STANDARD_ENVELOPE,
        "",
        "## Task",
        str(case["prompt"]),
        "",
        f"## Producer interface `{interface_id}`",
        (
            "This section discloses output structure and method evidence only. It "
            "contains no reference output or expected analytical result values."
        ),
        "Create exactly the artifacts below and no additional files under `outputs/`.",
    ]
    if interface_version >= 2:
        lines.extend(["", "### Execution hints"])
        lines.extend(f"- {hint}" for hint in interface["execution_hints"])
        lines.extend(["", "### Method contract"])
        lines.extend(f"- {rule}" for rule in interface["method_contract"])
    for artifact in interface["artifacts"]:
        lines.extend(["", *_artifact_block(artifact)])
    lines.extend(
        [
            "",
            (
                "Before finishing, verify every required field, CRS, unit, null, row, "
                "feature, and accessibility requirement against the local fixture."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=EXPECTED_CASE_IDS, required=True)
    parser.add_argument(
        "--interface-version",
        type=int,
        choices=(1, 2),
        default=1,
        help="frozen producer-interface version (default: 1)",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    """Render to stdout or one explicitly requested UTF-8 file."""
    args = parse_args()
    try:
        rendered = render_prompt(args.case, interface_version=args.interface_version)
        if args.output is None:
            sys.stdout.buffer.write(rendered.encode("utf-8"))
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8", newline="\n")
    except (OSError, TypeError, ValueError) as exc:
        print(f"ERROR: prompt rendering failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
