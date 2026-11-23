import pytest

from geoai_agents.checks import run_check
from geoai_agents.core import KIT, file_hash, json_bytes, read_json
from geoai_agents.evaluation import audit_run, compare, evaluate_pilots, prepare, verify_environment
from geoai_agents.integrity import verify_package


def test_all_six_pilots_have_valid_fault_and_missing_cases():
    result = evaluate_pilots()
    assert len(result["results"]) == 18
    assert result["exit_code"] == 0, result
    assert result["model_quality_measured"] is False


def test_bridge_is_not_a_false_obstacle(tmp_path):
    source = KIT / "evals/fixtures/walking-valid"
    for p in source.iterdir():
        (tmp_path / p.name).write_bytes(p.read_bytes())
    barriers = read_json(tmp_path / "barriers.geojson")
    barriers["features"][0]["geometry"]["coordinates"] = [
        [[40, -5], [60, -5], [60, 5], [40, 5], [40, -5]]]
    barriers["features"][0]["properties"]["kind"] = "water"
    (tmp_path / "barriers.geojson").write_bytes(json_bytes(barriers))
    spec = read_json(tmp_path / "check.json")
    assert run_check("walkability", tmp_path, spec)["exit_code"] == 1
    network = read_json(tmp_path / "network.geojson")
    network["features"][0]["properties"]["bridge"] = True
    (tmp_path / "network.geojson").write_bytes(json_bytes(network))
    assert run_check("walkability", tmp_path, spec)["exit_code"] == 0


def test_access_restriction_is_checked(tmp_path):
    source = KIT / "evals/fixtures/walking-valid"
    for p in source.iterdir():
        (tmp_path / p.name).write_bytes(p.read_bytes())
    network = read_json(tmp_path / "network.geojson")
    network["features"][0]["properties"]["foot_access"] = "no"
    (tmp_path / "network.geojson").write_bytes(json_bytes(network))
    assert run_check("walkability", tmp_path, read_json(tmp_path / "check.json"))["exit_code"] == 1


def test_hidden_width_legend_does_not_count(tmp_path):
    source = KIT / "evals/fixtures/line-meaning-valid"
    raw = (source / "map.svg").read_text().replace('id="width-legend"',
                                                 'id="width-legend" display="none"')
    (tmp_path / "map.svg").write_text(raw)
    result = run_check("line-semantics", tmp_path, read_json(source / "check.json"))
    assert result["exit_code"] == 1


@pytest.mark.parametrize("replace,with_text,expected", [
    ('<text id="width-legend"', '<g display="none"><text id="width-legend"', 1),
    ('<svg ', '<svg style="opacity:0" ', 2),
    ('points="100,20', 'points="120,20', 1),
])
def test_svg_inheritance_unsupported_style_and_gap(tmp_path, replace, with_text, expected):
    source = KIT / "evals/fixtures/line-meaning-valid"
    raw = (source / "map.svg").read_text().replace(replace, with_text)
    if '<g display="none">' in raw:
        raw = raw.replace('</text>', '</text></g>')
    (tmp_path / "map.svg").write_text(raw)
    assert run_check("line-semantics", tmp_path,
                     read_json(source / "check.json"))["exit_code"] == expected


def test_missing_or_malformed_evidence_abstains(tmp_path):
    assert run_check("not-implemented", tmp_path, {})["exit_code"] == 2
    assert run_check("spatial-split", tmp_path, {})["exit_code"] == 2
    (tmp_path / "map.svg").write_text("broken xml", encoding="utf-8")
    assert run_check("line-semantics", tmp_path, {"svg": "map.svg"})["exit_code"] == 2


def test_all_18_skills_have_positive_and_negative_scenarios():
    bindings = read_json(KIT / "bindings.json")
    cases = read_json(KIT / "evals/routing-cases.json")["cases"]
    assert len(cases) == 36
    assert set(bindings) == {c["skill"] for c in cases}
    for name in bindings:
        assert {c["id"].rsplit("/", 1)[1] for c in cases if c["skill"] == name} == {
            "positive", "negative"}


@pytest.mark.parametrize("runtime", ["codex", "claude"])
def test_comparison_preparation_keeps_answers_and_roles_out_of_baseline(tmp_path, runtime):
    result = prepare(tmp_path / "runs", KIT.parent / "skills", runtime)
    assert len(result["environments"]) == 54
    baseline = tmp_path / "runs" / runtime / "skills-only/case-001"
    team = tmp_path / "runs" / runtime / "agent-team/case-001"
    assert not (baseline / f".{runtime}/agents").exists()
    assert not (baseline / "toolkit/roles.json").exists()
    assert not list(baseline.rglob("pilots.json"))
    assert len(list((team / f".{runtime}/agents").iterdir())) == 6
    assert verify_package(team / ".geoai-agent-kit")["exit_code"] == 0
    assert (baseline / "inputs/case-001/route.geojson").read_bytes() == (
        team / "inputs/case-001/route.geojson").read_bytes()
    assert result["model_runs_started"] == 0
    assert verify_environment(baseline)["exit_code"] == 0
    (baseline / "AGENTS.md").write_text("unwanted instructions", encoding="utf-8")
    assert verify_environment(baseline)["exit_code"] == 1


def environment():
    return {"runtime": "codex", "condition": "skills-only", "case_id": "one",
            "producer_suite_sha256": "a" * 64, "expected_loaded_roles": []}


def completed_run():
    return {**environment(), "schema_version": 1, "kind": "evaluation-run",
            "producer_id": "producer", "latency_seconds": 2, "tokens": None, "cost_usd": None,
            "status": "completed", "runtime_version": "test-version",
            "model": "test-model", "trace_sha256": "b" * 64,
            "customization_inventory": {"complete": True, "roles": [],
                                         "external_instructions": [], "external_plugins": []}}


@pytest.mark.parametrize("change", [
    {"status": "quota-exhausted"}, {"trace_sha256": None},
    {"customization_inventory": {"complete": False}},
    {"customization_inventory": {"complete": True, "roles": ["geoai-specialist"]}},
    {"customization_inventory": {"complete": True, "external_instructions": ["AGENTS.md"]}},
])
def test_unknown_or_contaminated_model_run_is_excluded(change):
    run = {**completed_run(), **change}
    assert audit_run(environment(), run)["eligible"] is False


def test_compare_retains_exclusions_and_never_pools_runtimes():
    result = compare([environment()], [{**completed_run(), "status": "interrupted"}])
    assert len(result["excluded"]) == 1
    assert result["groups"] == {}
    assert result["pooled"] is False


def test_claimed_trace_without_bytes_cannot_be_eligible():
    assert not audit_run(environment(), completed_run())["eligible"]


def test_paired_comparison_uses_bound_judgments_and_excludes_changed_bytes(tmp_path):
    run = completed_run()
    profile = {**run["customization_inventory"], "source": "runtime-inspection"}
    run["customization_inventory"] = profile
    run.update(producer_id="producer", latency_seconds=2, tokens=10, cost_usd=None)
    for name, raw in {"trace": b"observed trace", "output": b"decision",
                      "profile_evidence": json_bytes(profile)}.items():
        path = tmp_path / (name + ".json")
        path.write_bytes(raw)
        run[name + "_path"] = path.name
        run[name + "_sha256"] = file_hash(path)
    judgment = {"output_sha256": run["output_sha256"], "reviewer_id": "reviewer",
                "status": "completed", "calculation": "pass", "evidence": "pass",
                "presentation": "not-applicable"}
    path = tmp_path / "judgment.json"
    path.write_bytes(json_bytes(judgment))
    run.update(judgment_path=path.name, judgment_sha256=file_hash(path))
    assert audit_run(environment(), run, tmp_path)["eligible"]
    result = compare([environment()], [run], [tmp_path])
    summary = next(iter(result["paired_summaries"].values()))
    assert summary["paired_case_ids"] == []  # one condition cannot imply improvement
    (tmp_path / "output.json").write_bytes(b"changed")
    assert not audit_run(environment(), run, tmp_path)["eligible"]
