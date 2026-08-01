"""Integrity and boundary tests for GeoAnalystBench artifact contracts v2."""

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
CONTRACTS = SUITE / "contracts" / "v2"
MANIFEST = SUITE / "freeze-v2.json"
FREEZE_TOOL = ROOT / "tools" / "build_external_eval_freeze_v2.py"
EXPECTED_CASE_IDS = [
    "gab-01-urban-heat",
    "gab-08-facility-coverage",
    "gab-36-vegetation-change",
    "gab-38-travel-time",
    "gab-39-spatial-regression",
]
EXPECTED_V1_SUITE_SHA256 = (
    "c99563100cacc1e03234edd82ec64f4f47dc9479ca2ca4f9aabe84a1d5373f12"
)
EXPECTED_V2_SUITE_SHA256 = (
    "86170ae144092f1ae0f34124d85505f0d3507a19f04f2b71f2081c89d10de418"
)


def load_freeze_module() -> ModuleType:
    """Load the v2 builder without making tools a runtime package."""
    spec = importlib.util.spec_from_file_location("external_eval_freeze_v2", FREEZE_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict:
    """Read one repository JSON object."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_committed_v2_contract_freeze_matches_sources() -> None:
    """Every contract byte and cross-reference must match freeze-v2."""
    module = load_freeze_module()
    assert module.validate_contracts_v2(SUITE) == []


def test_v2_freeze_is_canonical_and_keeps_v1_as_its_base() -> None:
    """The new taxonomy must not rewrite or silently replace frozen v1."""
    module = load_freeze_module()
    payload = read_json(MANIFEST)
    assert MANIFEST.read_bytes() == module.canonical_bytes(payload)
    assert payload["freeze_id"] == "geoanalystbench-derived-contracts-v2"
    assert payload["base_freeze_id"] == "geoanalystbench-derived-v1"
    assert payload["base_suite_sha256"] == EXPECTED_V1_SUITE_SHA256
    assert payload["suite_sha256"] == EXPECTED_V2_SUITE_SHA256
    assert payload["case_ids"] == EXPECTED_CASE_IDS
    assert payload["contract_axes"] == ["semantic", "evidence", "representation"]
    assert payload["results_included"] is False
    assert payload["native_suite_included"] is False
    assert payload["reporting_scope"] == "external-transfer-only"
    assert payload["strict_pass_rule"] == (
        "all-required-criteria-and-exact-inventory"  # noqa: S105 - outcome label
    )
    assert len(payload["files"]) == 6


def test_each_contract_separates_all_three_axes() -> None:
    """Substantive correctness cannot be conflated with field-name compliance."""
    v1 = read_json(SUITE / "freeze-v1.json")
    v1_hashes = {entry["path"]: entry["sha256"] for entry in v1["files"]}
    for case_id in EXPECTED_CASE_IDS:
        contract = read_json(CONTRACTS / f"{case_id}.json")
        case = read_json(SUITE / "cases" / case_id / "case.json")
        assert {item["axis"] for item in contract["criteria"]} == {
            "semantic",
            "evidence",
            "representation",
        }
        assert len({item["id"] for item in contract["criteria"]}) == len(
            contract["criteria"]
        )
        assert {item["path"] for item in contract["artifact_inventory"]} == set(
            case["expected_artifacts"]
        )
        assert contract["base_case_sha256"] == v1_hashes[
            f"cases/{case_id}/case.json"
        ]
        assert contract["strict_validator"]["sha256"] == v1_hashes[
            f"cases/{case_id}/validate_artifacts.py"
        ]


def test_v2_freeze_cli_check_passes() -> None:
    """The public verification command must pass without modifying sources."""
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
    assert "external contract freeze: pass" in result.stdout


def test_changed_contract_invalidates_v2_but_not_v1(tmp_path: Path) -> None:
    """A contract edit must fail v2 while the immutable v1 source remains valid."""
    copied = tmp_path / "geoanalystbench"
    shutil.copytree(SUITE, copied)
    contract = copied / "contracts" / "v2" / "gab-38-travel-time.json"
    contract.write_text(
        contract.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
        newline="\n",
    )

    module = load_freeze_module()
    assert module.validate_contract_sources(copied) == []
    errors = module.validate_freeze_manifest_v2(copied, copied / "freeze-v2.json")
    assert any("pinned v2 suite SHA-256" in error for error in errors)

    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from build_external_eval_freeze import validate_freeze_manifest

        assert validate_freeze_manifest(copied, copied / "freeze-v1.json") == []
    finally:
        sys.path.pop(0)


def test_unregistered_contract_is_rejected(tmp_path: Path) -> None:
    """An extra contract cannot silently enter the frozen denominator."""
    copied = tmp_path / "geoanalystbench"
    shutil.copytree(SUITE, copied)
    extra = copied / "contracts" / "v2" / "operator-notes.txt"
    extra.write_text("not part of the frozen contract layer\n", encoding="utf-8")

    module = load_freeze_module()
    errors = module.validate_contract_sources(copied)
    assert any("unregistered v2 contract file" in error for error in errors)
