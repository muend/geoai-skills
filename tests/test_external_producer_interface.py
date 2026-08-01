"""Integrity and disclosure tests for answer-safe producer interface v1."""

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
INTERFACES = SUITE / "producer-interfaces" / "v1"
MANIFEST = SUITE / "producer-interface-v1.json"
BUILD_TOOL = ROOT / "tools" / "build_external_producer_interface.py"
RENDER_TOOL = ROOT / "tools" / "render_external_case_prompt.py"
EXPECTED_INTERFACE_SHA256 = (
    "8596ddfeac83679c9a7c0b5007e5c009a44559823d8e70903bf5c66fd4274962"
)
EXPECTED_CASE_IDS = [
    "gab-01-urban-heat",
    "gab-08-facility-coverage",
    "gab-36-vegetation-change",
    "gab-38-travel-time",
    "gab-39-spatial-regression",
]


def load_builder() -> ModuleType:
    """Load the builder without making tools a runtime package."""
    spec = importlib.util.spec_from_file_location("producer_interface", BUILD_TOOL)
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
    """Render one prompt through the public deterministic CLI."""
    result = subprocess.run(  # noqa: S603 - repository-owned script
        [sys.executable, str(RENDER_TOOL), "--case", case_id],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_committed_producer_interface_matches_sources() -> None:
    """Every answer-safe interface byte must match its frozen manifest."""
    module = load_builder()
    assert module.validate_producer_interface(SUITE) == []
    payload = read_json(MANIFEST)
    assert MANIFEST.read_bytes() == module.canonical_bytes(payload)
    assert payload["interface_id"] == "geoanalystbench-producer-interface-v1"
    assert payload["suite_sha256"] == EXPECTED_INTERFACE_SHA256
    assert payload["case_ids"] == EXPECTED_CASE_IDS
    assert payload["reference_values_included"] is False
    assert payload["native_suite_included"] is False


def test_interfaces_match_v1_artifacts_without_answer_keys() -> None:
    """Producer guidance may expose shape but never answer-bearing keys."""
    module = load_builder()
    for case_id in EXPECTED_CASE_IDS:
        interface = read_json(INTERFACES / f"{case_id}.json")
        case = read_json(SUITE / "cases" / case_id / "case.json")
        assert {item["path"] for item in interface["artifacts"]} == set(
            case["expected_artifacts"]
        )
        assert module._find_forbidden_keys(interface) == []
        assert interface["disclosure_boundary"]["includes"] == [
            "artifact paths",
            "field names",
            "formats",
            "method evidence",
        ]


def test_rendered_prompts_are_deterministic_and_exclude_known_answers() -> None:
    """The model-facing layer must not disclose frozen reference outcomes."""
    known_answer_fragments = (
        "0.58848",
        "0.7125",
        "A>B>C>F",
        "0.349983",
        '"covered_population": 570',
    )
    for case_id in EXPECTED_CASE_IDS:
        first = render(case_id)
        assert first == render(case_id)
        assert "Producer interface `geoanalystbench-producer-interface-v1`" in first
        assert "Create exactly the artifacts below" in first
        assert "reference output or expected analytical result values" in first
        for fragment in known_answer_fragments:
            assert fragment not in first


def test_interface_cli_check_passes() -> None:
    """The public verification command must pass without rewriting sources."""
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
    assert "producer interface: pass" in result.stdout


def test_changed_or_extra_interface_file_is_rejected(tmp_path: Path) -> None:
    """Edits and unregistered files cannot silently change the prompt condition."""
    copied = tmp_path / "geoanalystbench"
    shutil.copytree(SUITE, copied)
    target = copied / "producer-interfaces" / "v1" / "gab-38-travel-time.json"
    target.write_text(
        target.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
        newline="\n",
    )
    extra = copied / "producer-interfaces" / "v1" / "operator-notes.txt"
    extra.write_text("not registered\n", encoding="utf-8", newline="\n")

    module = load_builder()
    errors = module.validate_producer_interface(copied)
    assert any("unregistered producer-interface file" in error for error in errors)
    assert any("pinned SHA-256" in error for error in errors)
