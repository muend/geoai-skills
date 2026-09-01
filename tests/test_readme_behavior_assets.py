"""Keep README behavior visuals pinned to their published evidence package."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "demo"
MANIFEST_PATH = ASSETS / "behavior-asset-manifest.json"
BENCHMARK = (
    ROOT
    / "benchmarks"
    / "claude-code-2.1.222--claude-sonnet-5--520bc41dd4c0"
    / "metrics.json"
)


def load_json(path: Path) -> dict:
    """Load a UTF-8 JSON object."""
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    """Return a file's lowercase SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_behavior_visual_asset_hashes_match_manifest() -> None:
    """Fail if a README visual changes without an explicit manifest update."""
    manifest = load_json(MANIFEST_PATH)
    pairs = [
        ("claim_gate", "geoai-claim-gate.gif", "gif_sha256"),
        ("claim_gate", "geoai-claim-gate-poster.png", "poster_sha256"),
        ("behavior_evidence", "geoai-behavior-evidence.gif", "gif_sha256"),
        (
            "behavior_evidence",
            "geoai-behavior-evidence-poster.png",
            "poster_sha256",
        ),
    ]

    for section, filename, field in pairs:
        assert sha256(ASSETS / filename) == manifest[section][field]


def test_behavior_visual_metrics_match_published_package() -> None:
    """Keep every displayed behavior number tied to the published metrics."""
    manifest = load_json(MANIFEST_PATH)
    metrics = load_json(BENCHMARK)
    visual = manifest["behavior_evidence"]
    results = metrics["behavior"]["results"]
    criterion = results["criterion_level"]
    case_level = results["case_level"]
    critical = results["critical_spatial_failure"]

    assert manifest["source"]["suite_sha256"] == metrics["suite_sha256"]
    assert manifest["source"]["run_date"] == metrics["run_date"]
    assert visual["responses_per_condition"] == metrics["conditions"][
        "skills-enabled"
    ]["responses"]
    assert visual["responses_per_condition"] == metrics["conditions"][
        "skills-disabled"
    ]["responses"]
    assert visual["clean_pairs"] == metrics["pairing"]["clean_matched_pairs"]

    assert visual["enabled_criterion_coverage"] in criterion["enabled_coverage"]
    assert visual["control_criterion_coverage"] in criterion["disabled_coverage"]
    assert visual["criterion_wins_losses_ties"] == (
        f"{criterion['wins_enabled']}/{criterion['wins_disabled']}/{criterion['ties']}"
    )
    assert math.isclose(
        float(visual["criterion_sign_test_p"]),
        criterion["sign_test"]["p_value"],
        rel_tol=0.02,
    )

    assert visual["enabled_all_criteria_met"].startswith(
        case_level["enabled_all_criteria_met"]
    )
    assert visual["control_all_criteria_met"].startswith(
        case_level["disabled_all_criteria_met"]
    )
    assert visual["all_criteria_wins_losses_ties"] == (
        f"{case_level['wins_enabled']}/{case_level['wins_disabled']}/"
        f"{case_level['ties']}"
    )
    assert math.isclose(
        float(visual["all_criteria_sign_test_p"]),
        case_level["sign_test"]["p_value"],
        rel_tol=0.02,
    )

    judged = critical["judged"]
    assert visual["enabled_critical_failures"] == (
        f"{critical['enabled']}/{judged} ({critical['enabled'] / judged:.1%})"
    )
    assert visual["control_critical_failures"] == (
        f"{critical['disabled']}/{judged} ({critical['disabled'] / judged:.1%})"
    )


def test_generated_visual_base_does_not_own_exact_copy() -> None:
    """Exact benchmark copy must remain deterministic rather than image-generated."""
    generation = load_json(MANIFEST_PATH)["visual_generation"]

    assert generation["generated_base_role"] == (
        "text-free cartographic illustration only"
    )
    assert generation["exact_text_generated_by_model"] is False
    assert "typography" in generation["deterministic_overlay"]
    assert "metrics" in generation["deterministic_overlay"]
