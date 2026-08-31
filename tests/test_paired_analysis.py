"""Tests for the paired enabled/disabled behavior analysis."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import paired_analysis as pa


# --------------------------------------------------------------------------
# sign test - the only statistical claim in the tool, so it is pinned hard
# --------------------------------------------------------------------------

def test_sign_test_no_discordant_pairs():
    r = pa.sign_test(0, 0)
    assert r["n"] == 0 and r["p_value"] is None


def test_sign_test_perfect_split_is_not_significant():
    r = pa.sign_test(5, 5)
    assert r["p_value"] == 1.0
    assert "not significant" in r["interpretation"]


def test_sign_test_known_values():
    # 16 wins, 0 losses -> p = 2 * (1/2)^16 = 3.0517578125e-05
    r = pa.sign_test(16, 0)
    assert r["p_value"] == pytest.approx(3.0517578125e-05, rel=1e-9)
    assert r["interpretation"] == "significant at p<0.001"
    # 6 vs 0 -> 2 * (1/64) = 0.03125
    assert pa.sign_test(6, 0)["p_value"] == pytest.approx(0.03125)
    # 5 vs 0 -> 0.0625, above 0.05
    assert pa.sign_test(5, 0)["interpretation"] == "not significant at p<0.05"


def test_sign_test_keeps_tiny_p_values_usable():
    """Fixed-decimal rounding would collapse a strong effect to 0.0; the stored
    value must survive at full precision and format correctly."""
    r = pa.sign_test(40, 0)
    assert r["p_value"] == pytest.approx(2 * 0.5 ** 40, rel=1e-12)
    assert r["p_value"] > 0.0
    assert pa._fmt_p(r["p_value"]) == "1.82e-12"
    assert pa._fmt_p(1.0) == "1.0000"
    assert pa._fmt_p(None) == "n/a"


def test_sign_test_is_symmetric():
    assert pa.sign_test(12, 3)["p_value"] == pa.sign_test(3, 12)["p_value"]


def test_sign_test_never_exceeds_one():
    for wins in range(0, 12):
        for losses in range(0, 12):
            p = pa.sign_test(wins, losses)["p_value"]
            assert p is None or 0.0 <= p <= 1.0


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------

def _case(cid, skill, critical=False, route=None, criteria=3):
    return {"case_id": cid, "skill": skill, "critical": critical,
            "expected_route": route or [skill], "tool_profile": "read-only",
            "expected_behavior": [f"c{i}" for i in range(criteria)]}


def _resp(cid, cost, skills, response="x" * 100, error=None, out_tokens=100):
    row = {"case_id": cid, "cost_usd": cost, "activated_skills": skills,
           "response": response, "latency_ms": 1000,
           "usage": {"output_tokens": out_tokens}}
    if error:
        row["error"] = error
    return row


def _judgment(cid, met_flags, critical_failure=False, forbidden=None):
    return {"case_id": cid, "critical_failure": critical_failure,
            "expected_behavior": [{"criterion": f"c{i}", "met": m, "evidence": ""}
                                  for i, m in enumerate(met_flags)],
            "forbidden_behavior": forbidden or []}


# --------------------------------------------------------------------------
# execution block
# --------------------------------------------------------------------------

def test_execution_counts_pairs_and_flags_control_contamination():
    cases = [_case("a/one", "a"), _case("b/two", "b")]
    en = {"a/one": _resp("a/one", 0.1, ["a"]), "b/two": _resp("b/two", 0.1, ["b"])}
    dis = {"a/one": _resp("a/one", 0.05, []), "b/two": _resp("b/two", 0.05, ["b"])}
    ex = pa.execution_block(cases, en, dis)
    assert ex["clean_matched_pairs"] == 2
    assert ex["activation"]["enabled"] == "2/2"
    assert ex["activation"]["disabled_control"] == "1/2"
    assert ex["activation"]["control_clean"] is False


def test_execution_excludes_errored_pairs_from_the_matched_set():
    cases = [_case("a/one", "a"), _case("b/two", "b")]
    en = {"a/one": _resp("a/one", 0.1, ["a"]),
          "b/two": _resp("b/two", 0.0, [], response="", error="max_turns")}
    dis = {"a/one": _resp("a/one", 0.05, []), "b/two": _resp("b/two", 0.05, [])}
    ex = pa.execution_block(cases, en, dis)
    assert ex["clean_matched_pairs"] == 1
    assert [e["case_id"] for e in ex["errored_pairs"]] == ["b/two"]
    assert ex["errored_pairs"][0]["enabled_error"] == "max_turns"


def test_execution_reports_route_shortfall():
    cases = [_case("a/one", "a", route=["a", "z"])]
    en = {"a/one": _resp("a/one", 0.1, ["a"])}
    dis = {"a/one": _resp("a/one", 0.05, [])}
    ex = pa.execution_block(cases, en, dis)
    assert ex["expected_route_satisfied"] == "0/1"
    assert ex["route_shortfalls"][0]["expected"] == ["a", "z"]


def test_execution_handles_partially_run_suite():
    cases = [_case("a/one", "a"), _case("b/two", "b")]
    en = {"a/one": _resp("a/one", 0.1, ["a"])}
    dis = {"a/one": _resp("a/one", 0.05, [])}
    ex = pa.execution_block(cases, en, dis)
    assert ex["cases_in_suite"] == 2
    assert ex["clean_matched_pairs"] == 1


# --------------------------------------------------------------------------
# judgment block
# --------------------------------------------------------------------------

def test_judgment_criterion_level_wins_and_ties():
    cases = [_case("a/one", "a", critical=True)]
    en_r = {"a/one": _resp("a/one", 0.1, ["a"])}
    dis_r = {"a/one": _resp("a/one", 0.05, [])}
    en_j = {"a/one": _judgment("a/one", [True, True, True])}
    dis_j = {"a/one": _judgment("a/one", [True, True, False])}
    j = pa.judgment_block(cases, en_j, dis_j, en_r, dis_r)
    assert j["criterion_level"]["wins_enabled"] == 1
    assert j["criterion_level"]["ties"] == 2
    assert j["case_level"]["wins_enabled"] == 1
    assert j["critical_subset_case_level"]["wins"] == 1


def test_judgment_tie_when_both_arms_meet_all_criteria():
    """A case both arms fully satisfy is a tie, not a win - the dilution effect
    addendum 02 was written about."""
    cases = [_case("a/one", "a", criteria=2)]
    en_r = {"a/one": _resp("a/one", 0.1, ["a"])}
    dis_r = {"a/one": _resp("a/one", 0.05, [])}
    en_j = {"a/one": _judgment("a/one", [True, True])}
    dis_j = {"a/one": _judgment("a/one", [True, True])}
    j = pa.judgment_block(cases, en_j, dis_j, en_r, dis_r)
    assert j["case_level"]["ties"] == 1
    assert j["case_level"]["sign_test"]["n"] == 0
    assert j["low_resolution_cases"]["count"] == 1


def test_judgment_disabled_can_win():
    cases = [_case("a/one", "a")]
    en_r = {"a/one": _resp("a/one", 0.1, ["a"])}
    dis_r = {"a/one": _resp("a/one", 0.05, [])}
    en_j = {"a/one": _judgment("a/one", [True, False, False])}
    dis_j = {"a/one": _judgment("a/one", [True, True, True])}
    j = pa.judgment_block(cases, en_j, dis_j, en_r, dis_r)
    assert j["case_level"]["wins_disabled"] == 1
    assert j["criterion_level"]["wins_disabled"] == 2


def test_judgment_skips_errored_cases():
    cases = [_case("a/one", "a")]
    en_r = {"a/one": _resp("a/one", 0.0, [], error="crash")}
    dis_r = {"a/one": _resp("a/one", 0.05, [])}
    en_j = {"a/one": _judgment("a/one", [True, True, True])}
    dis_j = {"a/one": _judgment("a/one", [False, False, False])}
    j = pa.judgment_block(cases, en_j, dis_j, en_r, dis_r)
    assert j["judged_pairs"] == 0


def test_judgment_counts_critical_failures_per_arm():
    cases = [_case("a/one", "a", critical=True)]
    en_r = {"a/one": _resp("a/one", 0.1, ["a"])}
    dis_r = {"a/one": _resp("a/one", 0.05, [])}
    en_j = {"a/one": _judgment("a/one", [True], critical_failure=False)}
    dis_j = {"a/one": _judgment("a/one", [False], critical_failure=True)}
    j = pa.judgment_block(cases, en_j, dis_j, en_r, dis_r)
    assert j["critical_spatial_failure"] == {"enabled": 0, "disabled": 1, "judged": 1}


def test_judgment_only_compares_criteria_present_in_both_arms():
    """Guards against a judge emitting a different criterion set for one arm."""
    cases = [_case("a/one", "a")]
    en_r = {"a/one": _resp("a/one", 0.1, ["a"])}
    dis_r = {"a/one": _resp("a/one", 0.05, [])}
    en_j = {"a/one": _judgment("a/one", [True, True, True])}
    dis_j = {"a/one": {"case_id": "a/one", "critical_failure": False,
                       "expected_behavior": [{"criterion": "c0", "met": False, "evidence": ""}],
                       "forbidden_behavior": []}}
    j = pa.judgment_block(cases, en_j, dis_j, en_r, dis_r)
    assert j["criterion_level"]["wins_enabled"] == 1
    assert j["criterion_level"]["ties"] == 0


# --------------------------------------------------------------------------
# end to end
# --------------------------------------------------------------------------

def _write_run(root: Path, condition: str, suite: str, cases, responses):
    d = root / f"claude-code-2-1-222--claude-sonnet-5--skills-{condition}--behavior--{suite}"
    (d / "adapter").mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({
        "suite_sha256": suite + "0" * (64 - len(suite)),
        "runtime": "claude-code-2.1.222", "model": "claude-sonnet-5",
        "condition": f"skills-{condition}", "cases": cases}), encoding="utf-8")
    (d / "adapter" / "claude-code.responses.jsonl").write_text(
        "\n".join(json.dumps(r) for r in responses), encoding="utf-8")
    return d


def test_main_runs_execution_only(tmp_path, capsys):
    suite = "abc123abc123"
    cases = [_case("a/one", "a"), _case("b/two", "b")]
    _write_run(tmp_path, "enabled", suite, cases,
               [_resp("a/one", 0.1, ["a"]), _resp("b/two", 0.1, ["b"])])
    _write_run(tmp_path, "disabled", suite, cases,
               [_resp("a/one", 0.05, []), _resp("b/two", 0.05, [])])
    rc = pa.main(["--suite", suite, "--runs-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "clean matched pairs      2" in out
    assert "CLEAN" in out
    assert "no judgments supplied" in out


def test_main_writes_json_and_includes_judgment(tmp_path, capsys):
    suite = "abc123abc123"
    cases = [_case("a/one", "a", critical=True)]
    _write_run(tmp_path, "enabled", suite, cases, [_resp("a/one", 0.1, ["a"])])
    _write_run(tmp_path, "disabled", suite, cases, [_resp("a/one", 0.05, [])])
    full = suite + "0" * (64 - len(suite))
    ej = tmp_path / "ej.json"
    dj = tmp_path / "dj.json"

    def judgment_set(flags):
        return json.dumps({
            "schema_version": 1,
            "suite_sha256": full,
            "judge": {"kind": "model", "name": "t"},
            "judgments": [_judgment("a/one", flags)],
        })

    ej.write_text(judgment_set([True, True, True]), encoding="utf-8")
    dj.write_text(judgment_set([True, False, False]), encoding="utf-8")
    out_json = tmp_path / "report.json"
    pa.main(["--suite", suite, "--runs-dir", str(tmp_path),
             "--enabled-judgments", str(ej), "--disabled-judgments", str(dj),
             "--json", str(out_json)])
    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert report["judgment"]["criterion_level"]["wins_enabled"] == 2
    assert "criterion level" in capsys.readouterr().out


def test_missing_run_directory_exits_cleanly(tmp_path):
    with pytest.raises(SystemExit):
        pa.main(["--suite", "nope", "--runs-dir", str(tmp_path)])


# --------------------------------------------------------------------------
# regression: retry and diagnostic directories must never be selected
# --------------------------------------------------------------------------

def test_run_dir_ignores_retry_and_diagnostic_suffixes(tmp_path):
    """A trailing wildcard matched `…--review-mode-retry-1` and sorted()[-1]
    picked it, so a completed 93-case run reported zero matched pairs."""
    suite = "abc123abc123"
    base = f"claude-code-2-1-222--claude-sonnet-5--skills-enabled--behavior--{suite}"
    for name in (base, base + "--review-mode-retry-1", base + "--maxturns12-diagnostic-1"):
        (tmp_path / name).mkdir()
    assert pa.run_dir(suite, "enabled", tmp_path).name == base


def test_run_dir_names_the_suffixed_directories_it_refused(tmp_path):
    suite = "abc123abc123"
    base = f"x--skills-enabled--behavior--{suite}"
    (tmp_path / (base + "--retry-1")).mkdir()
    with pytest.raises(SystemExit) as excinfo:
        pa.run_dir(suite, "enabled", tmp_path)
    assert "retry-1" in str(excinfo.value)


def test_run_dir_refuses_ambiguity_rather_than_guessing(tmp_path):
    suite = "abc123abc123"
    for prefix in ("aaa", "bbb"):
        (tmp_path / f"{prefix}--skills-enabled--behavior--{suite}").mkdir()
    with pytest.raises(SystemExit) as excinfo:
        pa.run_dir(suite, "enabled", tmp_path)
    assert "ambiguous" in str(excinfo.value)


def test_run_dir_runtime_filter_separates_prepared_runtimes(tmp_path):
    """Both 2.1.214 and 2.1.222 prepared this suite; only the latter ran."""
    suite = "abc123abc123"
    for rt in ("claude-code-2-1-214", "claude-code-2-1-222"):
        (tmp_path / f"{rt}--claude-sonnet-5--skills-enabled--behavior--{suite}").mkdir()
    with pytest.raises(SystemExit) as excinfo:
        pa.run_dir(suite, "enabled", tmp_path)
    assert "--runtime" in str(excinfo.value)
    picked = pa.run_dir(suite, "enabled", tmp_path, "claude-code-2-1-222")
    assert picked.name.startswith("claude-code-2-1-222")
