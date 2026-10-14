from copy import deepcopy

import pytest

from geoai_agents.checks import run_check
from geoai_agents.core import KIT, file_hash, json_bytes, read_json
from geoai_agents.evaluation import CONDITIONS, audit_run, compare


@pytest.fixture
def bound_run(tmp_path):
    environment = {"runtime": "codex", "condition": "skills-only", "case_id": "one",
                   "producer_suite_sha256": "a" * 64, "expected_loaded_roles": []}
    profile = {"complete": True, "source": "runtime-inspection", "roles": [],
               "external_instructions": [], "external_plugins": []}
    run = {**environment, "schema_version": 1, "kind": "evaluation-run",
           "producer_id": "producer", "latency_seconds": 2, "tokens": None,
           "cost_usd": None, "status": "completed", "runtime_version": "version-one",
           "model": "model-one", "customization_inventory": profile}
    for name, raw in {"trace": b"trace", "output": b"output",
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
    return environment, run, tmp_path


@pytest.mark.parametrize("malformed", [None, [], {"runtime": []}])
def test_malformed_run_is_excluded_without_crashing(bound_run, malformed):
    env, _, root = bound_run
    assert not audit_run(env, malformed, root)["eligible"]
    result = compare([env], [malformed], [root])
    assert not result["groups"]
    assert len(result["excluded"]) == 1


@pytest.mark.parametrize("roles", [None, [1, "geoai-specialist"]])
def test_malformed_role_inventory_is_excluded(bound_run, roles):
    env, run, root = bound_run
    run["customization_inventory"]["roles"] = roles
    assert not audit_run(env, run, root)["eligible"]


@pytest.mark.parametrize("field", ["model", "runtime_version"])
def test_separate_model_or_runtime_groups_keep_all_three_conditions(bound_run, field):
    env, run, root = bound_run
    environments = [{**env, "condition": condition} for condition in CONDITIONS]
    runs = [{**deepcopy(run), "condition": condition, field: value}
            for value in ("one", "two") for condition in CONDITIONS]
    result = compare(environments, runs, [root] * len(runs))
    assert result["excluded"] == []
    assert result["missing_runs"] == 0
    assert len(result["paired_summaries"]) == 2
    for summary in result["paired_summaries"].values():
        assert summary["paired_case_ids"] == ["one"]
        assert all(c["matched_cases"] == 1 for c in summary["conditions"].values())


def test_duplicate_identity_excludes_both_runs_without_order_bias(bound_run):
    env, run, root = bound_run
    interrupted = {**run, "status": "interrupted"}
    for runs in ([run, interrupted], [interrupted, run]):
        result = compare([env], runs, [root, root])
        assert not result["groups"]
        assert len(result["excluded"]) == 2


def test_model_names_with_slashes_cannot_merge_distinct_groups(bound_run):
    env, run, root = bound_run
    runs = [{**run, "runtime_version": "v1", "model": "provider/model"},
            {**run, "runtime_version": "v1/provider", "model": "model"}]
    result = compare([env], runs, [root, root])
    assert len(result["groups"]) == 2
    assert result["excluded"] == []


@pytest.mark.parametrize("reviewer", [True, 123, [], ""])
def test_judgment_requires_a_nonempty_string_identity(bound_run, reviewer):
    env, run, root = bound_run
    path = root / run["judgment_path"]
    judgment = read_json(path)
    judgment["reviewer_id"] = reviewer
    path.write_bytes(json_bytes(judgment))
    run["judgment_sha256"] = file_hash(path)
    assert not audit_run(env, run, root)["eligible"]


@pytest.mark.parametrize("wrapper,attribute", [
    ("defs", ""), ("symbol", ""), ("g", 'fill="none"'),
    ("g", 'fill-opacity="0"'), ("g", 'font-size="0"'),
])
def test_unrendered_width_legend_cannot_pass(bound_run, wrapper, attribute):
    _, _, root = bound_run
    source = KIT / "evals/fixtures/line-meaning-valid"
    raw = (source / "map.svg").read_text(encoding="utf-8")
    raw = raw.replace('<text id="width-legend"',
                      f'<{wrapper} {attribute}><text id="width-legend"')
    raw = raw.replace("</text>", f"</text></{wrapper}>")
    (root / "map.svg").write_text(raw, encoding="utf-8")
    result = run_check("line-semantics", root, read_json(source / "check.json"))
    assert result["exit_code"] != 0


def test_invalid_geojson_geometry_abstains(bound_run):
    _, _, root = bound_run
    source = KIT / "evals/fixtures/walking-valid"
    for path in source.iterdir():
        (root / path.name).write_bytes(path.read_bytes())
    network = read_json(root / "network.geojson")
    network["features"][0]["geometry"] = None
    (root / "network.geojson").write_bytes(json_bytes(network))
    result = run_check("walkability", root, read_json(source / "check.json"))
    assert result["exit_code"] == 2
