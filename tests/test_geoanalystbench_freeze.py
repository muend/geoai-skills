"""Integrity tests for the frozen GeoAnalystBench-derived v1 source subset."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
SUITE = ROOT / "evals" / "external" / "geoanalystbench"
MANIFEST = SUITE / "freeze-v1.json"
FREEZE_TOOL = ROOT / "tools" / "build_external_eval_freeze.py"
EXPECTED_CASE_IDS = [
    "gab-01-urban-heat",
    "gab-08-facility-coverage",
    "gab-36-vegetation-change",
    "gab-38-travel-time",
    "gab-39-spatial-regression",
]
EXPECTED_SUITE_SHA256 = (
    "c99563100cacc1e03234edd82ec64f4f47dc9479ca2ca4f9aabe84a1d5373f12"
)


def load_freeze_module() -> ModuleType:
    """Load the freeze builder without making tools a runtime package."""
    spec = importlib.util.spec_from_file_location("external_eval_freeze", FREEZE_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_freeze_matches_current_sources() -> None:
    """Every governed byte must match the committed v1 manifest."""
    module = load_freeze_module()
    assert module.validate_freeze_manifest(SUITE, MANIFEST) == []


def test_freeze_manifest_is_canonical_and_boundary_explicit() -> None:
    """The freeze must be deterministic and must not imply benchmark results."""
    module = load_freeze_module()
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert MANIFEST.read_bytes() == module.canonical_bytes(payload)
    assert payload["freeze_id"] == "geoanalystbench-derived-v1"
    assert payload["case_ids"] == EXPECTED_CASE_IDS
    assert payload["upstream_task_ids"] == [1, 8, 36, 38, 39]
    assert payload["native_suite_included"] is False
    assert payload["results_included"] is False
    assert payload["reporting_scope"] == "external-transfer-only"
    assert payload["suite_sha256"] == EXPECTED_SUITE_SHA256
    assert len(payload["files"]) == 24


def test_freeze_cli_check_passes() -> None:
    """The public operator command must verify the committed freeze."""
    result = subprocess.run(  # noqa: S603 - repo-owned interpreter and script
        [sys.executable, str(FREEZE_TOOL), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "external freeze: pass" in result.stdout


def test_freeze_rejects_changed_source_bytes(tmp_path: Path) -> None:
    """A plausible source edit must invalidate v1 until a new freeze is made."""
    copied = tmp_path / "geoanalystbench"
    shutil.copytree(SUITE, copied)
    case_path = copied / "cases" / "gab-38-travel-time" / "case.json"
    case_path.write_text(
        case_path.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
        newline="\n",
    )

    module = load_freeze_module()
    errors = module.validate_freeze_manifest(copied, copied / "freeze-v1.json")
    assert any("frozen source hash changed" in error for error in errors)
    assert any("suite_sha256" in error for error in errors)


def test_freeze_rejects_unregistered_source_file(tmp_path: Path) -> None:
    """New case-local source material must not silently enter frozen v1."""
    copied = tmp_path / "geoanalystbench"
    shutil.copytree(SUITE, copied)
    extra = copied / "cases" / "gab-01-urban-heat" / "postprocess.py"
    extra.write_text("raise SystemExit('not part of v1')\n", encoding="utf-8")

    module = load_freeze_module()
    errors = module.validate_freeze_manifest(copied, copied / "freeze-v1.json")
    assert any("unfrozen source file added" in error for error in errors)
