"""Integrity and disclosure tests for semantic producer interface v3."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
SUITE = ROOT / "evals" / "external" / "geoanalystbench"
INTERFACES = SUITE / "producer-interfaces" / "v3"
MANIFEST = SUITE / "producer-interface-v3.json"
BUILD_TOOL = ROOT / "tools" / "build_external_producer_interface_v3.py"
RENDER_TOOL = ROOT / "tools" / "render_external_case_prompt.py"
EXPECTED_INTERFACE_SHA256 = (
    "f52aadf2bfc3db74e2e004f647696f1b0c9631154823ee02fb433e2daff6b754"
)
EXPECTED_CASE_IDS = [
    "gab-01-urban-heat",
    "gab-08-facility-coverage",
    "gab-36-vegetation-change",
    "gab-38-travel-time",
    "gab-39-spatial-regression",
]


def load_builder() -> ModuleType:
    """Load the v3 builder without making tools a runtime package."""
    spec = importlib.util.spec_from_file_location("producer_interface_v3", BUILD_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def read_json(path: Path) -> dict:
    """Read one repository JSON object."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def render(case_id: str) -> str:
    """Render one v3 prompt through the deterministic CLI."""
    result = subprocess.run(  # noqa: S603 - repository-owned script
        [
            sys.executable,
            str(RENDER_TOOL),
            "--case",
            case_id,
            "--interface-version",
            "3",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_committed_v3_interface_matches_sources() -> None:
    """Every v3 byte must match its immutable semantic-interface manifest."""
    module = load_builder()
    assert module.validate_producer_interface_v3(SUITE) == []
    payload = read_json(MANIFEST)
    assert MANIFEST.read_bytes() == module.canonical_bytes(payload)
    assert payload["interface_id"] == "geoanalystbench-producer-interface-v3"
    assert payload["suite_sha256"] == EXPECTED_INTERFACE_SHA256
    assert payload["contract_freeze_id"] == (
        "geoanalystbench-derived-contracts-v3"
    )
    assert payload["case_ids"] == EXPECTED_CASE_IDS
    assert payload["supersedes"] == "geoanalystbench-producer-interface-v2"
    assert payload["reference_values_included"] is False


def test_v3_discloses_semantic_structure_without_answer_keys() -> None:
    """Nested structures and serialization rules may be public; outcomes may not."""
    module = load_builder()
    for case_id in EXPECTED_CASE_IDS:
        interface = read_json(INTERFACES / f"{case_id}.json")
        case = read_json(SUITE / "cases" / case_id / "case.json")
        assert {item["path"] for item in interface["artifacts"]} == set(
            case["expected_artifacts"]
        )
        assert interface["execution_hints"]
        assert interface["method_contract"]
        assert module.find_forbidden_keys(interface) == []


def test_v3_closes_observed_v2_ambiguities() -> None:
    """The v3 condition must encode the formatting and structure lessons from v2."""
    vegetation = json.dumps(
        read_json(INTERFACES / "gab-36-vegetation-change.json")
    )
    travel = json.dumps(read_json(INTERFACES / "gab-38-travel-time.json"))
    urban = json.dumps(read_json(INTERFACES / "gab-01-urban-heat.json"))
    regression = json.dumps(
        read_json(INTERFACES / "gab-39-spatial-regression.json")
    )
    for threshold in ("-0.150", "-0.200", "-0.250"):
        assert threshold in vegetation
    assert "ordered JSON array" in travel
    assert "nested" in urban
    assert "seed+3" in regression
    assert "vectorized" in regression


def test_v3_prompts_are_deterministic_and_exclude_known_outcomes() -> None:
    """Semantic guidance must not expose frozen analytical result values."""
    known_outcome_fragments = (
        "0.58848",
        "0.7125",
        "A>B>C>F",
        "0.349983",
        '"covered_population": 570',
    )
    for case_id in EXPECTED_CASE_IDS:
        first = render(case_id)
        assert first == render(case_id)
        assert "Producer interface `geoanalystbench-producer-interface-v3`" in first
        assert "### Execution hints" in first
        assert "### Method contract" in first
        for fragment in known_outcome_fragments:
            assert fragment not in first


def test_v3_interface_cli_check_passes() -> None:
    """The public v3 verification command must pass without rewriting sources."""
    result = subprocess.run(  # noqa: S603 - repository-owned script
        [sys.executable, str(BUILD_TOOL), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "producer interface v3: pass" in result.stdout
