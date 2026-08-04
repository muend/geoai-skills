"""Integrity and semantic-equivalence tests for artifact contract v3."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent
SUITE = ROOT / "evals" / "external" / "geoanalystbench"
CASES = SUITE / "cases"
VALIDATOR = SUITE / "validators" / "v3" / "validate_artifacts.py"
MANIFEST = SUITE / "freeze-v3.json"
FREEZE_TOOL = ROOT / "tools" / "build_external_eval_freeze_v3.py"
EXPECTED_V3_SHA256 = (
    "e17b9ee3f6d69ba99aacc90cab998339bf0f679c76ce25645e09a70e882ad3f2"
)
CASE_FIXTURES = {
    "gab-01-urban-heat": "urban-heat.json",
    "gab-08-facility-coverage": "coverage-network.json",
    "gab-36-vegetation-change": "hailstorm-scenes.json",
    "gab-38-travel-time": "network.json",
    "gab-39-spatial-regression": "spatial-regression.json",
}


def load_builder() -> ModuleType:
    """Load the v3 builder without making tools a runtime package."""
    spec = importlib.util.spec_from_file_location("external_eval_freeze_v3", FREEZE_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def run_script(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run one repository-owned offline helper."""
    return subprocess.run(  # noqa: S603 - frozen repository script
        [sys.executable, str(script), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )


def build_reference(case_id: str, root: Path) -> tuple[Path, Path]:
    """Generate one deterministic fixture and its independent reference outputs."""
    case_dir = CASES / case_id
    fixture_dir = root / "fixtures"
    output_dir = root / "outputs"
    generated = run_script(
        case_dir / "generate_fixture.py", "--output-dir", str(fixture_dir)
    )
    assert generated.returncode == 0, generated.stderr
    input_path = fixture_dir / CASE_FIXTURES[case_id]
    referenced = run_script(
        case_dir / "reference.py",
        "--input",
        str(input_path),
        "--output-dir",
        str(output_dir),
    )
    assert referenced.returncode == 0, referenced.stderr
    return input_path, output_dir


def validate(input_path: Path, output_dir: Path) -> subprocess.CompletedProcess[str]:
    """Run the universal semantic v3 validator."""
    return run_script(
        VALIDATOR,
        "--input",
        str(input_path),
        "--output-dir",
        str(output_dir),
    )


def test_committed_v3_contract_freeze_matches_the_validator() -> None:
    """The semantic validator and immutable manifest must remain byte-pinned."""
    module = load_builder()
    assert module.validate_contract_v3(SUITE) == []
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert payload["freeze_id"] == "geoanalystbench-derived-contracts-v3"
    assert payload["suite_sha256"] == EXPECTED_V3_SHA256
    assert payload["supersedes"] == "geoanalystbench-derived-contracts-v2"
    assert payload["strict_pass_rule"] == (
        "all-required-semantic-criteria-and-exact-inventory"  # noqa: S105
    )
    assert MANIFEST.read_bytes() == module.canonical_bytes(payload)


@pytest.mark.parametrize("case_id", list(CASE_FIXTURES))
def test_reference_outputs_satisfy_v3_semantics(
    tmp_path: Path,
    case_id: str,
) -> None:
    """All five frozen reference producers must satisfy the new semantic layer."""
    input_path, output_dir = build_reference(case_id, tmp_path / case_id)
    result = validate(input_path, output_dir)
    assert result.returncode == 0, result.stderr
    assert "artifact contract v3" in result.stdout


def test_v3_accepts_equivalent_svg_bytes_but_rejects_numeric_corruption(
    tmp_path: Path,
) -> None:
    """Representation freedom must not weaken analytical correctness."""
    input_path, output_dir = build_reference("gab-01-urban-heat", tmp_path)
    svg = output_dir / "urban-heat-map.svg"
    svg.write_text(
        svg.read_text(encoding="utf-8") + "\n<!-- equivalent rendering -->\n",
        encoding="utf-8",
        newline="\n",
    )
    equivalent = validate(input_path, output_dir)
    assert equivalent.returncode == 0, equivalent.stderr

    surface = output_dir / "temperature-surface.json"
    payload = json.loads(surface.read_text(encoding="utf-8"))
    payload["values"][0][0] += 0.01
    surface.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    corrupted = validate(input_path, output_dir)
    assert corrupted.returncode == 1
    assert "semantic oracle" in corrupted.stderr


def test_v3_freeze_cli_check_passes() -> None:
    """The public v3 verification command must pass without rewriting sources."""
    result = run_script(FREEZE_TOOL, "--check")
    assert result.returncode == 0, result.stderr
    assert "external contract v3: pass" in result.stdout
