"""The CLI must abstain on malformed input, never crash.

Found during the 2026-07-26 security audit of this toolkit: a malformed payload
raised `TypeError`/`ValueError` out of the command handler, so the process died
with exit code 1 — which this tool *defines* as "FAILED, a violation was found".
An unreadable input and a real violation produced the same signal, which is
exactly the conflation the three-outcome vocabulary exists to prevent.

Worse in context: a CI step that crashes with a traceback looks like a failing
check. An operator would go looking for a violation that was never found, and
anyone wrapping the call in `|| true` would convert the crash into silence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import verify

EXIT_VERIFIED = 0
EXIT_FAILED = 1
EXIT_NOT_VERIFIED = 2


def write(tmp_path: Path, name: str, payload: object) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


# --- malformed payloads must abstain -------------------------------------


def test_unknown_scene_field_abstains(tmp_path: Path) -> None:
    path = write(tmp_path, "scenes.json", [{"label": "a", "evil_key": 1}])

    assert verify.main(["comparability", "--scenes", path]) == EXIT_NOT_VERIFIED


def test_non_numeric_equity_value_abstains(tmp_path: Path) -> None:
    path = write(tmp_path, "groups.json", {"north": ["not-a-number"]})

    assert verify.main(["equity", "--groups", path]) == EXIT_NOT_VERIFIED


def test_non_numeric_count_abstains(tmp_path: Path) -> None:
    path = write(tmp_path, "counts.json", {"cell": "abc"})

    assert verify.main(["privacy", "--counts", path]) == EXIT_NOT_VERIFIED


def test_non_numeric_p_value_abstains(tmp_path: Path) -> None:
    path = write(tmp_path, "p.json", ["nope"])

    assert (
        verify.main(["multiplicity", "--p-values", path, "--reported", "1"])
        == EXIT_NOT_VERIFIED
    )


def test_out_of_range_p_value_abstains(tmp_path: Path) -> None:
    """The check itself rejects these; the CLI must surface it as abstention."""
    path = write(tmp_path, "p.json", [0.1, 2.0])

    assert (
        verify.main(["multiplicity", "--p-values", path, "--reported", "1"])
        == EXIT_NOT_VERIFIED
    )


def test_non_object_metadata_abstains(tmp_path: Path) -> None:
    path = write(tmp_path, "meta.json", ["a list, not an object"])

    assert (
        verify.main(["parameters", "choropleth", "--metadata", path])
        == EXIT_NOT_VERIFIED
    )


def test_non_object_manifest_abstains(tmp_path: Path) -> None:
    path = write(tmp_path, "manifest.json", ["not a manifest"])

    assert verify.main(["provenance", "--manifest", path]) == EXIT_NOT_VERIFIED


def test_missing_file_abstains(tmp_path: Path) -> None:
    assert (
        verify.main(["provenance", "--manifest", str(tmp_path / "absent.json")])
        == EXIT_NOT_VERIFIED
    )


def test_unparseable_json_abstains(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    assert verify.main(["provenance", "--manifest", str(path)]) == EXIT_NOT_VERIFIED


def test_class_breaks_with_non_numeric_edges_abstains(tmp_path: Path) -> None:
    path = write(tmp_path, "breaks.json", {"2020": ["a", "b"], "2024": ["c", "d"]})

    assert (
        verify.main(["comparability", "--class-breaks", path]) == EXIT_NOT_VERIFIED
    )


# --- valid input still behaves ------------------------------------------


def test_a_real_violation_still_exits_one(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "groups.json",
        {"north": [10, 11], "centre": [9, 9], "south": [40, 41]},
    )

    assert verify.main(["equity", "--groups", path]) == EXIT_FAILED


def test_a_clean_check_exits_zero() -> None:
    assert verify.main(["units", "buffer", "--crs", "EPSG:32633"]) == EXIT_VERIFIED


def test_a_wrong_unit_exits_one() -> None:
    assert verify.main(["units", "buffer", "--crs", "EPSG:4326"]) == EXIT_FAILED


def test_an_unknown_crs_exits_two() -> None:
    assert verify.main(["units", "buffer", "--crs", "EPSG:99999999"]) == EXIT_NOT_VERIFIED


def test_shared_class_breaks_exit_zero(tmp_path: Path) -> None:
    path = write(tmp_path, "breaks.json", {"2020": [0, 10, 20], "2024": [0, 10, 20]})

    assert verify.main(["comparability", "--class-breaks", path]) == EXIT_VERIFIED


# --- the invariant the exit codes encode --------------------------------


def test_failure_outranks_abstention_in_the_exit_code(tmp_path: Path) -> None:
    """One command can produce both; a violation must not be masked."""
    scenes = write(
        tmp_path,
        "scenes.json",
        [
            {"label": "a", "sensor": "S2", "processing_level": "L1C", "acquired_month": 7},
            {"label": "b", "sensor": "S2", "processing_level": "L2A", "acquired_month": 7},
        ],
    )
    breaks = write(tmp_path, "breaks.json", {"2020": ["x"], "2024": ["y"]})

    code = verify.main(
        ["comparability", "--scenes", scenes, "--class-breaks", breaks]
    )

    assert code == EXIT_FAILED


def test_json_output_is_still_valid_on_abstention(tmp_path: Path, capsys) -> None:
    path = write(tmp_path, "counts.json", {"cell": "abc"})

    verify.main(["--json", "privacy", "--counts", path])
    payload = json.loads(capsys.readouterr().out)

    assert payload["exit_code"] == EXIT_NOT_VERIFIED
    assert payload["results"][0]["outcome"] == "abstain"


@pytest.mark.parametrize(
    "argv",
    [
        ["units", "buffer", "--crs", "EPSG:4326"],
        ["ordering", "composite", "cloud_mask"],
    ],
)
def test_no_command_path_raises(argv: list[str]) -> None:
    """Every subcommand returns an exit code rather than propagating."""
    assert verify.main(argv) in {EXIT_VERIFIED, EXIT_FAILED, EXIT_NOT_VERIFIED}
