"""Separate addon evaluation: offline validators and contamination-aware run records."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .checks import run_check
from .core import (
    KIT, contained, file_hash, finite, inventory, json_bytes, outcome, read_json,
    records, report, write_new,
)
from .distribution import adapters, package_manifest, payload
from .integrity import base_manifest, tree_digest, verify_base, verify_inventory

CONDITIONS = ("skills-only", "structured-single", "agent-team")
ENVIRONMENT_ID = ("runtime", "condition", "case_id", "producer_suite_sha256")
RUN_ID = (*ENVIRONMENT_ID, "runtime_version", "model")


def _valid_run(record: Any) -> bool:
    from jsonschema import Draft202012Validator

    schema = read_json(KIT / "schemas/evaluation-run.schema.json")
    return Draft202012Validator(schema).is_valid(record)


def evaluate_pilots() -> dict[str, Any]:
    suite = read_json(KIT / "evals" / "pilots.json")
    results = []
    for case in suite["cases"]:
        result = run_check(case["check"], KIT / "evals" / "fixtures" / case["id"], case["spec"])
        actual = result["results"][0]["outcome"]
        results.append({"case_id": case["id"], "expected": case["expected"], "actual": actual,
                        "matched": actual == case["expected"], "report": result})
    return {"schema_version": 1, "kind": "deterministic-pilot-report",
            "suite_sha256": tree_digest(records(KIT / "evals", inventory(KIT / "evals"))),
            "model_quality_measured": False, "results": results,
            "exit_code": 0 if all(r["matched"] for r in results) else 1}


def prepare(destination: Path, skills_root: Path, runtime: str) -> dict[str, Any]:
    """Stage matched inputs/tools in three fresh roots; never stage expected answers."""
    if destination.exists():
        raise FileExistsError("evaluation destination must be new")
    if verify_base(skills_root, skills_only=True)["exit_code"]:
        raise ValueError("base skills do not match")
    base = base_manifest()
    skill_files = [r["path"][7:] for r in base["files"] if r["path"].startswith("skills/")]
    inputs = read_json(KIT / "evals" / "producer-cases.json")
    suite_names = ["producer-cases.json"] + ["producer-inputs/" + n
                  for n in inventory(KIT / "evals/producer-inputs")]
    suite_sha = tree_digest(records(KIT / "evals", suite_names))
    environments = []
    tools = payload()
    runtime_manifest = package_manifest(tools)
    # These artifacts expose the same tools, but no role instructions, to every condition.
    shared = {k: v for k, v in tools.items() if k.startswith(("runtime/", "_vendor/", "schemas/"))
              or k in {"geoai_agents.py", "package.json", "base.lock.json", "bindings.json",
                       "controls.json", "source.lock.json"}}
    for condition in CONDITIONS:
        for case in inputs["cases"]:
            root = destination / runtime / condition / case["id"]
            files = {f"toolkit/{k}": v for k, v in shared.items()}
            for name in skill_files:
                prefix = ".agents/skills" if runtime == "codex" else ".claude/skills"
                files[f"{prefix}/{name}"] = contained(skills_root, name).read_bytes()
            for name in case["inputs"]:
                source = contained(KIT / "evals" / "producer-inputs", name)
                files[f"inputs/{name}"] = source.read_bytes()
            prompt = case["prompt"] + "\nDo not read outside this workspace.\n"
            if condition != "skills-only":
                prompt += inputs["structured_protocol"]
            if condition == "agent-team":
                prompt += inputs["team_protocol"]
                files.update({f".geoai-agent-kit/{k}": v for k, v in tools.items()})
                files[".geoai-agent-kit/manifest.json"] = json_bytes(runtime_manifest)
                files[".geoai-agent-kit/installation.json"] = json_bytes({
                    "schema_version": 1, "runtime": runtime,
                    "skills_root": str((root / prefix).resolve()), "base": base["base"],
                    "agent_runtime_sha256": runtime_manifest["agent_runtime_sha256"]})
                for name, raw in adapters().items():
                    if name.startswith(f"adapters/{runtime}/"):
                        files[f".{runtime}/agents/{Path(name).name}"] = raw
            files["REQUEST.txt"] = prompt.encode("utf-8")
            for name, raw in files.items():
                write_new(contained(root, name), raw)
            evidence = records(root, inventory(root))
            manifest = {"schema_version": 1, "runtime": runtime, "condition": condition,
                        "case_id": case["id"], "producer_suite_sha256": suite_sha,
                        "workspace_files": evidence, "expected_loaded_roles":
                        ["geoai-" + r["id"] for r in read_json(KIT / "roles.json")]
                        if condition == "agent-team" else [],
                        "requires_isolated_runtime_profile": True}
            write_new(root / "environment.json", json_bytes(manifest))
            environments.append(str(root))
    return {"exit_code": 0, "environments": environments, "model_runs_started": 0,
            "producer_suite_sha256": suite_sha}


def audit_run(environment: dict[str, Any], record: Any,
              evidence_root: Path | None = None) -> dict[str, Any]:
    """Exclude unknown profiles and contamination, rather than trusting a success exit."""
    reasons = []
    reasons.extend(environment.get("isolation_issues", []))
    note = "Profile inspection is an attestation, not an OS isolation certificate."
    if not _valid_run(record):
        reasons.append("invalid evaluation run contract")
        return {"eligible": False, "reasons": reasons, "note": note}
    for key in ("latency_seconds", "tokens", "cost_usd"):
        try:
            if record.get(key) is not None and finite(record[key]) < 0:
                reasons.append(f"negative {key}")
        except ValueError:
            reasons.append(f"invalid {key}")
    if record.get("status") != "completed":
        reasons.append("run did not complete")
    for key in ("runtime", "condition", "case_id", "producer_suite_sha256"):
        if record.get(key) != environment.get(key):
            reasons.append(f"identity mismatch: {key}")
    trace = record.get("customization_inventory")
    if not isinstance(trace, dict) or trace.get("complete") is not True:
        reasons.append("loaded customizations were not established")
    else:
        if trace.get("external_instructions") or trace.get("external_plugins"):
            reasons.append("external instruction/plugin contamination")
        if sorted(trace.get("roles", [])) != sorted(environment["expected_loaded_roles"]):
            reasons.append("agent definitions differ from the declared condition")
    if not record.get("model") or not record.get("runtime_version"):
        reasons.append("runtime/model not pinned")
    if not record.get("trace_sha256"):
        reasons.append("runtime trace missing")
    if evidence_root is None:
        reasons.append("run evidence directory unavailable")
    else:
        for key in ("trace", "output", "profile_evidence", "judgment"):
            try:
                path = contained(evidence_root, record[key + "_path"])
                if file_hash(path) != record[key + "_sha256"]:
                    reasons.append(f"changed {key} evidence")
            except (OSError, KeyError, ValueError, TypeError):
                reasons.append(f"missing {key} evidence")
        try:
            profile = read_json(contained(evidence_root, record["profile_evidence_path"]))
            if profile != trace or profile.get("source") != "runtime-inspection":
                reasons.append("profile inventory does not match inspected evidence")
        except (OSError, KeyError, ValueError, TypeError):
            reasons.append("profile evidence unavailable")
        try:
            judged = read_json(contained(evidence_root, record["judgment_path"]))
            if judged["output_sha256"] != record["output_sha256"]:
                reasons.append("judgment refers to a different output")
            if (not isinstance(judged["reviewer_id"], str) or not judged["reviewer_id"].strip()
                    or judged["reviewer_id"] == record.get("producer_id")
                    or judged["status"] != "completed"):
                reasons.append("independent judgment incomplete")
            for dimension in ("calculation", "evidence", "presentation"):
                if judged[dimension] not in {"pass", "fail", "abstain", "not-applicable"}:
                    reasons.append("invalid judgment dimension")
        except (OSError, KeyError, ValueError, TypeError):
            reasons.append("judgment evidence unavailable")
    return {"eligible": not reasons, "reasons": reasons, "note": note}


def verify_environment(root: Path) -> dict[str, Any]:
    entries = read_json(root / "environment.json")["workspace_files"]
    results = verify_inventory(root, entries)["results"]
    protected = (".codex/", ".claude/", ".agents/", ".geoai-agent-kit/", "toolkit/", "inputs/")
    expected = {e["path"] for e in entries}
    extras = [p for p in inventory(root) if p not in expected and
              (p.startswith(protected) or p in {"AGENTS.md", "CLAUDE.md"})]
    if extras:
        results.append(outcome("evaluation-contamination", "fail",
                               "Unexpected instruction or immutable input", files=extras))
    return report(results)


def compare(environments: list[dict[str, Any]], runs: list[Any],
            evidence_roots: list[Path] | None = None) -> dict[str, Any]:
    """Retain exclusions, report each runtime/model separately; no pooled headline."""
    if evidence_roots is not None and len(evidence_roots) != len(runs):
        raise ValueError("each run must have a corresponding evidence directory")
    indexed = {tuple(e[k] for k in ENVIRONMENT_ID): e for e in environments}
    valid = [_valid_run(run) for run in runs]
    counts = Counter(tuple(run[k] for k in RUN_ID)
                     for run, ok in zip(runs, valid, strict=True) if ok)
    groups: dict[str, Any] = {}
    excluded = []
    seen = set()
    for index, run in enumerate(runs):
        if not valid[index]:
            excluded.append({"run_index": index,
                             "reasons": ["invalid evaluation run contract"]})
            continue
        key = tuple(run[k] for k in ENVIRONMENT_ID)
        identity = {k: run[k] for k in RUN_ID}
        if key not in indexed:
            excluded.append({**identity, "reasons": ["unknown environment"]})
            continue
        seen.add(key)
        if counts[tuple(run[k] for k in RUN_ID)] > 1:
            excluded.append({**identity, "reasons": ["duplicate run identity"]})
            continue
        evidence_root = evidence_roots[index] if evidence_roots is not None else None
        audit = audit_run(indexed[key], run, evidence_root)
        if not audit["eligible"]:
            excluded.append({**identity, **audit})
            continue
        group_key = "/".join(quote(run[k], safe="") for k in
                             ("runtime", "runtime_version", "model", "producer_suite_sha256"))
        group = groups.setdefault(group_key, {})
        judgment = read_json(contained(evidence_root, run["judgment_path"]))
        group.setdefault(run["condition"], []).append({
            **{k: run.get(k) for k in ("case_id", "latency_seconds", "tokens", "cost_usd")},
            "judgment": judgment})
    summaries = {}
    for key, group in groups.items():
        paired = set.intersection(*(set(r["case_id"] for r in group.get(c, []))
                                    for c in CONDITIONS))
        summaries[key] = {"paired_case_ids": sorted(paired), "conditions": {}}
        for condition, rows in group.items():
            matched = [r for r in rows if r["case_id"] in paired]
            dims = [r["judgment"][d] for r in matched
                    for d in ("calculation", "evidence", "presentation")
                    if r["judgment"][d] != "not-applicable"]
            summaries[key]["conditions"][condition] = {
                "matched_cases": len(matched),
                "criterion_pass_rate": dims.count("pass") / len(dims) if dims else None,
                "latency_seconds": sum(r["latency_seconds"] for r in matched)
                if matched and all(r["latency_seconds"] is not None for r in matched) else None,
                "cost_usd": sum(r["cost_usd"] for r in matched)
                if matched and all(r["cost_usd"] is not None for r in matched) else None}
    return {"schema_version": 1, "groups": groups, "excluded": excluded,
            "missing_runs": len(indexed) - len(seen), "pooled": False,
            "paired_summaries": summaries,
            "quality_claim": "No superiority claim; inspect matched independent judgments."}
