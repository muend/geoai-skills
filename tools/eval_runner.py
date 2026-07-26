#!/usr/bin/env python3
"""Prepare, compose, ingest, and score reproducible GeoAI Skills evaluation runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
EVAL_SCHEMA_PATH = ROOT / "evals" / "schema.json"
RUN_SCHEMA_PATH = ROOT / "evals" / "run-schema.json"
DEFAULT_RUNS_DIR = ROOT / "evals" / "runs"
INTERACTION_MODES = ("clarify", "deliver", "clarify_then_provisional")


class EvalRunnerError(RuntimeError):
    """Raised when an evaluation run violates a deterministic contract."""


def canonical_json(value: Any) -> str:
    """Return the canonical JSON representation used for hashes and comparisons."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def zero_failure_upper_bound_95(evaluated_cases: int, failures: int) -> float | None:
    """Return the exact one-sided 95% failure-rate bound for zero observed failures."""
    if evaluated_cases <= 0 or failures != 0:
        return None
    return 1.0 - (0.05 ** (1.0 / evaluated_cases))


def repository_relative(path: Path, *, repository_root: Path = ROOT) -> str:
    try:
        return path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError as exc:
        raise EvalRunnerError(f"Path escapes repository root: {path}") from exc


def normalize_fixture(
    eval_dir: Path,
    raw_fixture: dict[str, Any],
    *,
    repository_root: Path = ROOT,
) -> dict[str, Any]:
    source = (eval_dir / raw_fixture["source"]).resolve()
    try:
        source.relative_to((eval_dir / "fixtures").resolve())
    except ValueError as exc:
        raise EvalRunnerError(
            f"Fixture escapes fixture root: {raw_fixture['source']}"
        ) from exc
    if not source.is_file():
        raise EvalRunnerError(f"Missing fixture file: {source}")
    content = source.read_bytes()
    digest = sha256_bytes(content)
    declared = raw_fixture.get("sha256")
    if declared is not None and declared != digest:
        # The derived hash alone only detects drift within one process. A
        # declared hash makes the fixture's content reviewable in the diff: a
        # pull request that changes fixture bytes must also change this line,
        # so the swap cannot pass as an unrelated edit.
        raise EvalRunnerError(
            f"Fixture content does not match the declared sha256 for "
            f"{raw_fixture['source']}: declared {declared}, actual {digest}"
        )
    return {
        "source_path": repository_relative(source, repository_root=repository_root),
        "workspace_path": raw_fixture["workspace_path"],
        "sha256": digest,
        "size_bytes": len(content),
    }


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EvalRunnerError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EvalRunnerError(f"Invalid JSON in {path}: {exc}") from exc


def load_jsonl(path: Path) -> list[Any]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise EvalRunnerError(f"Missing file: {path}") from exc

    rows: list[Any] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise EvalRunnerError(
                f"Invalid JSON in {path}:{line_number}: {exc}"
            ) from exc
    return rows


def pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def jsonl_text(rows: Iterable[Any]) -> str:
    return "".join(canonical_json(row) + "\n" for row in rows)


def write_immutable(path: Path, content: str, *, force: bool = False) -> bool:
    """Write content atomically, refusing a different overwrite unless forced."""
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == content:
            return False
        if not force:
            raise EvalRunnerError(
                f"Refusing to overwrite different content at {path}; use --force intentionally"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)
    return True


def contract_validator(
    run_schema: dict[str, Any], definition: str
) -> Draft202012Validator:
    if definition not in run_schema.get("$defs", {}):
        raise EvalRunnerError(f"Unknown run contract: {definition}")
    schema = {
        "$schema": run_schema["$schema"],
        "$defs": run_schema["$defs"],
        "$ref": f"#/$defs/{definition}",
    }
    return Draft202012Validator(schema)


def validate_instance(
    validator: Draft202012Validator,
    value: Any,
    *,
    label: str,
) -> None:
    issues = sorted(
        validator.iter_errors(value), key=lambda issue: list(issue.absolute_path)
    )
    if not issues:
        return
    rendered = []
    for issue in issues:
        location = "/".join(str(part) for part in issue.absolute_path) or "<root>"
        rendered.append(f"{label}:{location}: {issue.message}")
    raise EvalRunnerError("\n".join(rendered))


def validate_unique_exact_ids(
    rows: list[dict[str, Any]],
    expected_ids: list[str],
    *,
    label: str,
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for row in rows:
        case_id = row.get("case_id") if isinstance(row, dict) else None
        if case_id in indexed:
            duplicates.add(str(case_id))
        elif isinstance(case_id, str):
            indexed[case_id] = row
    if duplicates:
        raise EvalRunnerError(
            f"{label} contains duplicate case ids: {', '.join(sorted(duplicates))}"
        )

    expected = set(expected_ids)
    actual = set(indexed)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    problems = []
    if missing:
        problems.append(f"missing: {', '.join(missing)}")
    if extra:
        problems.append(f"unexpected: {', '.join(extra)}")
    if problems:
        raise EvalRunnerError(f"{label} case coverage mismatch ({'; '.join(problems)})")
    return indexed


def load_suite(
    *,
    skills_dir: Path = SKILLS,
    eval_schema_path: Path = EVAL_SCHEMA_PATH,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    """Load, normalize, validate, and hash the complete evaluation suite."""
    eval_schema = load_json(eval_schema_path)
    Draft202012Validator.check_schema(eval_schema)
    validator = Draft202012Validator(eval_schema)
    cases: list[dict[str, Any]] = []
    skill_names: list[str] = []

    for skill_dir in sorted(path for path in skills_dir.iterdir() if path.is_dir()):
        skill_path = skill_dir / "SKILL.md"
        eval_path = skill_dir / "evals" / "evals.json"
        if not skill_path.exists() or not eval_path.exists():
            raise EvalRunnerError(
                f"{skill_dir.name}: SKILL.md and evals/evals.json are required"
            )
        data = load_json(eval_path)
        issues = sorted(
            validator.iter_errors(data), key=lambda issue: list(issue.absolute_path)
        )
        if issues:
            details = []
            for issue in issues:
                location = (
                    "/".join(str(part) for part in issue.absolute_path) or "<root>"
                )
                details.append(f"{eval_path}:{location}: {issue.message}")
            raise EvalRunnerError("\n".join(details))
        if data["skill"] != skill_dir.name:
            raise EvalRunnerError(
                f"{eval_path}: skill '{data['skill']}' does not match folder '{skill_dir.name}'"
            )

        skill_names.append(skill_dir.name)
        skill_sha256 = sha256_bytes(skill_path.read_bytes())
        for raw_case in data["evals"]:
            fixtures = [
                normalize_fixture(
                    eval_path.parent,
                    fixture,
                    repository_root=skills_dir.parent,
                )
                for fixture in raw_case.get("fixtures", [])
            ]
            workspace_paths = [fixture["workspace_path"] for fixture in fixtures]
            if len(workspace_paths) != len(set(workspace_paths)):
                raise EvalRunnerError(
                    f"{eval_path}:{raw_case['id']}: duplicate fixture workspace paths"
                )
            expected_artifacts = [
                {
                    "path": artifact["path"],
                    "media_type": artifact["media_type"],
                    "required": artifact.get("required", True),
                }
                for artifact in raw_case.get("expected_artifacts", [])
            ]
            artifact_paths = [artifact["path"] for artifact in expected_artifacts]
            if len(artifact_paths) != len(set(artifact_paths)):
                raise EvalRunnerError(
                    f"{eval_path}:{raw_case['id']}: duplicate expected artifact paths"
                )
            overlap = sorted(set(workspace_paths) & set(artifact_paths))
            if overlap:
                raise EvalRunnerError(
                    f"{eval_path}:{raw_case['id']}: fixture/output path overlap: "
                    + ", ".join(overlap)
                )
            normalized = {
                "case_id": f"{skill_dir.name}/{raw_case['id']}",
                "skill": skill_dir.name,
                "eval_id": raw_case["id"],
                "prompt": raw_case["prompt"],
                "case_types": raw_case["case_types"],
                "should_trigger": raw_case.get("should_trigger", True),
                "expected_route": sorted(raw_case.get("expected_route", [])),
                "expected_behavior": raw_case["expected_behavior"],
                "forbidden_behavior": raw_case.get("forbidden_behavior", []),
                "critical": raw_case.get("critical", False),
                "behavior_class": raw_case.get("behavior_class", "routing-only"),
                "tool_profile": raw_case.get("tool_profile", "read-only"),
                "fixtures": fixtures,
                "expected_artifacts": expected_artifacts,
                "skill_sha256": skill_sha256,
            }
            if "interaction_mode" in raw_case:
                normalized["interaction_mode"] = raw_case["interaction_mode"]
            normalized["case_sha256"] = sha256_json(normalized)
            cases.append(normalized)

    cases.sort(key=lambda case: case["case_id"])
    ids = [case["case_id"] for case in cases]
    if len(ids) != len(set(ids)):
        duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
        raise EvalRunnerError(f"Duplicate global case ids: {', '.join(duplicates)}")
    suite_sha256 = sha256_json(cases)
    return cases, suite_sha256, sorted(skill_names)


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized[:60] or "unknown"


VALID_SPLITS = ("all", "dev", "holdout")
DEFAULT_SPLIT_PATH = ROOT / "evals" / "split.json"


def load_split_ids(split: str, split_path: Path) -> set[str] | None:
    """Case ids belonging to one half of the dev / held-out split.

    Returns None for `all`, so callers can distinguish "no filter" from "an
    empty half" — the second is an error and must not silently behave like the
    first.
    """
    if split == "all":
        return None
    if split not in VALID_SPLITS:
        raise EvalRunnerError(f"split must be one of {list(VALID_SPLITS)}")
    if not split_path.exists():
        raise EvalRunnerError(
            f"{split_path} is missing, so '{split}' does not name a set of cases. "
            f"Generate it with `python tools/build_split.py --write`."
        )
    payload = load_json(split_path)
    ids = set(payload.get(split) or ())
    if not ids:
        raise EvalRunnerError(f"the '{split}' half of {split_path} is empty")
    return ids


def select_cases(
    cases: list[dict[str, Any]],
    *,
    evaluation_scope: str = "all",
    split: str = "all",
    split_path: Path | None = None,
) -> list[dict[str, Any]]:
    """The single definition of "which cases does this run cover".

    Both regression gates and `prepare` read it, so a benchmark's declared
    population and the population the harness actually ran cannot drift apart.

    Two independent filters:

    * `evaluation_scope` — only `behavior` narrows, to the cases carrying
      criteria. `routing` deliberately keeps every case, because activation is
      observable on a behaviour case too: it still tells you whether the right
      skill fired. `routing-only` marks a case as not behaviour-judged, not as
      the population routing is measured on. Filtering it here would silently
      shrink routing measurement to a subset of the suite.
    * `split` — which half of the dev / held-out split.

    Order is preserved, because the suite hash is computed over this list.
    """
    if evaluation_scope not in {"routing", "behavior", "all"}:
        raise EvalRunnerError("evaluation_scope must be routing, behavior, or all")
    selected = cases
    if evaluation_scope == "behavior":
        selected = [c for c in selected if c["behavior_class"] != "routing-only"]
        if not selected:
            raise EvalRunnerError(
                "behavior scope has no explicitly behavior-evaluable cases"
            )
    ids = load_split_ids(split, split_path or DEFAULT_SPLIT_PATH)
    if ids is not None:
        selected = [c for c in selected if c["case_id"] in ids]
        if not selected:
            raise EvalRunnerError(
                f"the '{split}' half contains no cases in scope '{evaluation_scope}'"
            )
    return selected


def prepare_run(
    *,
    runtime: str,
    model: str,
    condition: str,
    evaluation_scope: str = "all",
    split: str = "all",
    runs_dir: Path = DEFAULT_RUNS_DIR,
    run_id: str | None = None,
    skills_dir: Path = SKILLS,
    eval_schema_path: Path = EVAL_SCHEMA_PATH,
    run_schema_path: Path = RUN_SCHEMA_PATH,
    split_path: Path = DEFAULT_SPLIT_PATH,
) -> Path:
    if condition not in {"skills-enabled", "skills-disabled"}:
        raise EvalRunnerError("condition must be skills-enabled or skills-disabled")
    cases, _, skill_names = load_suite(
        skills_dir=skills_dir,
        eval_schema_path=eval_schema_path,
    )
    cases = select_cases(
        cases,
        evaluation_scope=evaluation_scope,
        split=split,
        split_path=split_path,
    )
    suite_sha256 = sha256_json(cases)
    run_schema = load_json(run_schema_path)
    Draft202012Validator.check_schema(run_schema)
    manifest = {
        "kind": "geoai-eval-manifest",
        "schema_version": 1,
        "suite_sha256": suite_sha256,
        "runtime": runtime,
        "model": model,
        "condition": condition,
        "evaluation_scope": evaluation_scope,
        "split": split,
        "available_skills": skill_names if condition == "skills-enabled" else [],
        "cases": cases,
    }
    validate_instance(
        contract_validator(run_schema, "manifest"), manifest, label="manifest"
    )

    split_tag = "" if split == "all" else f"--{split}"
    selected_id = run_id or (
        f"{slug(runtime)}--{slug(model)}--{condition}--{evaluation_scope}"
        f"{split_tag}--{suite_sha256[:12]}"
    )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", selected_id):
        raise EvalRunnerError("run-id must be 1-200 safe filename characters")
    run_dir = runs_dir / selected_id
    requests = [
        {"schema_version": 1, "case_id": case["case_id"], "prompt": case["prompt"]}
        for case in cases
    ]
    request_validator = contract_validator(run_schema, "request")
    for index, request in enumerate(requests, start=1):
        validate_instance(request_validator, request, label=f"request[{index}]")

    write_immutable(run_dir / "manifest.json", pretty_json(manifest))
    write_immutable(run_dir / "requests.jsonl", jsonl_text(requests))
    return run_dir


def load_manifest(run_dir: Path, run_schema: dict[str, Any]) -> dict[str, Any]:
    manifest = load_json(run_dir / "manifest.json")
    validate_instance(
        contract_validator(run_schema, "manifest"), manifest, label="manifest"
    )
    return manifest


def validate_response_context(
    *,
    manifest: dict[str, Any],
    cases: list[dict[str, Any]],
    responses: dict[str, dict[str, Any]],
) -> None:
    """Ensure cached responses still belong to the declared run and suite."""
    known_skills = set(manifest["available_skills"])
    for case in cases:
        row = responses[case["case_id"]]
        for field in ("runtime", "model", "condition"):
            if row[field] != manifest[field]:
                raise EvalRunnerError(
                    f"{case['case_id']}: response {field} '{row[field]}' "
                    f"does not match manifest '{manifest[field]}'"
                )
        unknown = sorted(set(row["activated_skills"]) - known_skills)
        if unknown:
            raise EvalRunnerError(
                f"{case['case_id']}: unknown activated skills: {', '.join(unknown)}"
            )


def resolve_run_response_path(run_dir: Path, relative_path: Path) -> Path:
    """Resolve a response file below a run directory without allowing traversal."""
    if relative_path.is_absolute():
        raise EvalRunnerError("response-relative-path must be relative")
    resolved_run = run_dir.resolve()
    resolved_path = (resolved_run / relative_path).resolve()
    try:
        resolved_path.relative_to(resolved_run)
    except ValueError as exc:
        raise EvalRunnerError(
            f"Response path escapes source run directory: {relative_path}"
        ) from exc
    return resolved_path


def index_source_responses(
    *,
    source_run: Path,
    response_relative_path: Path,
    run_schema: dict[str, Any],
) -> tuple[dict[str, Any], Path, dict[str, dict[str, Any]]]:
    """Load and validate a possibly partial adapter response batch."""
    manifest = load_manifest(source_run, run_schema)
    response_path = resolve_run_response_path(source_run, response_relative_path)
    rows = load_jsonl(response_path)
    response_validator = contract_validator(run_schema, "response")
    for index, row in enumerate(rows, start=1):
        validate_instance(
            response_validator,
            row,
            label=f"{source_run.name} response[{index}]",
        )

    indexed: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for row in rows:
        case_id = row["case_id"]
        if case_id in indexed:
            duplicates.add(case_id)
        else:
            indexed[case_id] = row
    if duplicates:
        raise EvalRunnerError(
            f"{source_run.name} contains duplicate case ids: "
            f"{', '.join(sorted(duplicates))}"
        )

    source_cases = {case["case_id"]: case for case in manifest["cases"]}
    unexpected = sorted(set(indexed) - set(source_cases))
    if unexpected:
        raise EvalRunnerError(
            f"{source_run.name} contains responses outside its manifest: "
            f"{', '.join(unexpected)}"
        )
    selected_cases = [source_cases[case_id] for case_id in indexed]
    validate_response_context(
        manifest=manifest,
        cases=selected_cases,
        responses=indexed,
    )
    return manifest, response_path, indexed


def compose_responses(
    *,
    run_dir: Path,
    primary_run: Path,
    replacement_runs: list[Path] | None = None,
    replacement_case_ids: list[str] | None = None,
    response_relative_path: Path = Path("adapter/claude-code.responses.jsonl"),
    force: bool = False,
    run_schema_path: Path = RUN_SCHEMA_PATH,
) -> Path:
    """Compose a complete response batch from a primary run and explicit retries."""
    run_schema = load_json(run_schema_path)
    target_manifest = load_manifest(run_dir, run_schema)
    target_cases = {
        case["case_id"]: case for case in target_manifest["cases"]
    }
    target_ids = [case["case_id"] for case in target_manifest["cases"]]

    sources = [("primary", primary_run)]
    sources.extend(
        ("replacement", replacement_run)
        for replacement_run in (replacement_runs or [])
    )
    requested_replacements: set[str] | None = None
    if replacement_case_ids is not None:
        requested_replacements = set(replacement_case_ids)
        if len(requested_replacements) != len(replacement_case_ids):
            raise EvalRunnerError("replacement-case-id values must be unique")
    composed: dict[str, dict[str, Any]] = {}
    replacement_ids: set[str] = set()
    provenance_sources: list[dict[str, Any]] = []

    for role, source_run in sources:
        source_manifest, response_path, indexed = index_source_responses(
            source_run=source_run,
            response_relative_path=response_relative_path,
            run_schema=run_schema,
        )
        for field in ("runtime", "model", "condition"):
            if source_manifest[field] != target_manifest[field]:
                raise EvalRunnerError(
                    f"{source_run.name}: source {field} "
                    f"'{source_manifest[field]}' does not match target "
                    f"'{target_manifest[field]}'"
                )

        source_cases = {
            case["case_id"]: case for case in source_manifest["cases"]
        }
        if role == "primary":
            selected_ids = [
                case_id for case_id in target_ids if case_id in indexed
            ]
        elif requested_replacements is None:
            selected_ids = list(indexed)
        else:
            selected_ids = [
                case_id
                for case_id in target_ids
                if case_id in indexed and case_id in requested_replacements
            ]
        if role == "primary":
            missing_primary = sorted(set(target_ids) - set(selected_ids))
            if missing_primary:
                raise EvalRunnerError(
                    f"{source_run.name}: primary responses do not cover target cases: "
                    f"{', '.join(missing_primary)}"
                )
        outside_target = sorted(set(selected_ids) - set(target_cases))
        if outside_target:
            raise EvalRunnerError(
                f"{source_run.name}: replacement responses outside target scope: "
                f"{', '.join(outside_target)}"
            )
        if role == "replacement":
            overlap = sorted(replacement_ids & set(selected_ids))
            if overlap:
                raise EvalRunnerError(
                    "Replacement runs overlap for case ids: "
                    f"{', '.join(overlap)}"
                )
            replacement_ids.update(selected_ids)

        for case_id in selected_ids:
            source_case = source_cases[case_id]
            target_case = target_cases[case_id]
            if source_case["case_sha256"] != target_case["case_sha256"]:
                raise EvalRunnerError(
                    f"{case_id}: source case hash does not match target manifest"
                )
            composed[case_id] = indexed[case_id]

        provenance_sources.append(
            {
                "role": role,
                "run": source_run.resolve().as_posix(),
                "response_path": response_relative_path.as_posix(),
                "response_file_sha256": sha256_bytes(response_path.read_bytes()),
                "selected_case_ids": selected_ids,
                "ignored_case_ids": sorted(set(indexed) - set(selected_ids)),
                "selected_response_sha256": {
                    case_id: sha256_json(indexed[case_id])
                    for case_id in selected_ids
                },
            }
        )

    if requested_replacements is not None:
        missing_replacements = sorted(requested_replacements - replacement_ids)
        if missing_replacements:
            raise EvalRunnerError(
                "Requested replacement case ids were not found exactly once: "
                f"{', '.join(missing_replacements)}"
            )
    missing = sorted(set(target_ids) - set(composed))
    if missing:
        raise EvalRunnerError(
            f"Primary and replacement runs do not cover target cases: "
            f"{', '.join(missing)}"
        )

    ordered = [composed[case_id] for case_id in target_ids]
    validate_response_context(
        manifest=target_manifest,
        cases=target_manifest["cases"],
        responses=composed,
    )
    output_path = run_dir / "adapter" / "composed.responses.jsonl"
    output_text = jsonl_text(ordered)
    write_immutable(output_path, output_text, force=force)
    provenance = {
        "schema_version": 1,
        "target_run": run_dir.resolve().as_posix(),
        "target_suite_sha256": target_manifest["suite_sha256"],
        "output_path": output_path.resolve().as_posix(),
        "output_sha256": sha256_bytes(output_text.encode("utf-8")),
        "response_count": len(ordered),
        "sources": provenance_sources,
    }
    write_immutable(
        run_dir / "adapter" / "composed.provenance.json",
        pretty_json(provenance),
        force=force,
    )
    return output_path


def ingest_responses(
    *,
    run_dir: Path,
    input_path: Path,
    force: bool = False,
    run_schema_path: Path = RUN_SCHEMA_PATH,
) -> Path:
    run_schema = load_json(run_schema_path)
    manifest = load_manifest(run_dir, run_schema)
    rows = load_jsonl(input_path)
    response_validator = contract_validator(run_schema, "response")
    for index, row in enumerate(rows, start=1):
        validate_instance(response_validator, row, label=f"response[{index}]")

    cases = manifest["cases"]
    expected_ids = [case["case_id"] for case in cases]
    indexed = validate_unique_exact_ids(rows, expected_ids, label="responses")
    validate_response_context(manifest=manifest, cases=cases, responses=indexed)
    normalized = []
    for case in cases:
        row = indexed[case["case_id"]]
        normalized.append(row)

    raw_path = run_dir / "raw" / "responses.jsonl"
    write_immutable(raw_path, jsonl_text(normalized), force=force)
    for case, row in zip(cases, normalized, strict=True):
        cache_path = run_dir / "cache" / f"{case['case_sha256']}.json"
        write_immutable(cache_path, pretty_json(row), force=force)
    return raw_path


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def score_run(
    *,
    run_dir: Path,
    judgments_path: Path,
    routing_only: bool = False,
    force: bool = False,
    run_schema_path: Path = RUN_SCHEMA_PATH,
) -> Path:
    run_schema = load_json(run_schema_path)
    manifest = load_manifest(run_dir, run_schema)
    response_rows = load_jsonl(run_dir / "raw" / "responses.jsonl")
    response_validator = contract_validator(run_schema, "response")
    for index, row in enumerate(response_rows, start=1):
        validate_instance(response_validator, row, label=f"cached response[{index}]")

    cases = manifest["cases"]
    expected_ids = [case["case_id"] for case in cases]
    responses = validate_unique_exact_ids(
        response_rows, expected_ids, label="cached responses"
    )
    validate_response_context(manifest=manifest, cases=cases, responses=responses)

    judgment_set = load_json(judgments_path)
    validate_instance(
        contract_validator(run_schema, "judgmentSet"),
        judgment_set,
        label="judgments",
    )
    if judgment_set["suite_sha256"] != manifest["suite_sha256"]:
        raise EvalRunnerError("Judgment suite_sha256 does not match the manifest")
    behavior_cases = (
        []
        if routing_only or manifest.get("evaluation_scope", "all") == "routing"
        else [
            case
            for case in cases
            if case.get("behavior_class", "advisory") != "routing-only"
        ]
    )
    behavior_ids = [case["case_id"] for case in behavior_cases]
    judgments = validate_unique_exact_ids(
        judgment_set["judgments"], behavior_ids, label="judgments"
    )

    case_results = []
    counts = {"tp": 0, "tn": 0, "fp": 0, "fn": 0}
    route_matches = 0
    behavior_passes = 0
    criteria_met = 0
    criteria_total = 0
    forbidden_violations = 0
    critical_evaluated = 0
    critical_failures = 0
    interaction_metrics = {
        mode: {"passed_cases": 0, "judged_cases": 0} for mode in INTERACTION_MODES
    }
    input_tokens = 0
    output_tokens = 0
    latency_ms = 0
    cost_usd = 0.0

    for case in cases:
        case_id = case["case_id"]
        response = responses[case_id]
        behavior_evaluated = case_id in judgments
        judgment = judgments.get(case_id)
        if judgment is not None:
            expected_criteria = [
                check["criterion"] for check in judgment["expected_behavior"]
            ]
            forbidden_criteria = [
                check["criterion"] for check in judgment["forbidden_behavior"]
            ]
            if expected_criteria != case["expected_behavior"]:
                raise EvalRunnerError(
                    f"{case_id}: expected_behavior criteria drift from manifest"
                )
            if forbidden_criteria != case["forbidden_behavior"]:
                raise EvalRunnerError(
                    f"{case_id}: forbidden_behavior criteria drift from manifest"
                )

        activated = set(response["activated_skills"])
        target_active = case["skill"] in activated
        if case["should_trigger"]:
            outcome = "tp" if target_active else "fn"
            expected_route = set(case["expected_route"] or [case["skill"]])
            route_match = target_active and expected_route.issubset(activated)
        else:
            outcome = "fp" if target_active else "tn"
            expected_route = set(case["expected_route"])
            route_match = not target_active and expected_route.issubset(activated)
        counts[outcome] += 1
        route_matches += int(route_match)

        met = (
            sum(int(check["met"]) for check in judgment["expected_behavior"])
            if judgment is not None
            else 0
        )
        expected_total = (
            len(judgment["expected_behavior"]) if judgment is not None else 0
        )
        violations = (
            sum(int(check["observed"]) for check in judgment["forbidden_behavior"])
            if judgment is not None
            else 0
        )
        response_error = bool(response.get("error"))
        behavior_pass = (
            (
                met == expected_total
                and violations == 0
                and not judgment["critical_failure"]
                and not response_error
            )
            if judgment is not None
            else None
        )
        behavior_passes += int(bool(behavior_pass))
        if behavior_evaluated:
            criteria_met += met
            criteria_total += expected_total
            forbidden_violations += violations
            interaction_mode = case.get("interaction_mode", "deliver")
            interaction_metrics[interaction_mode]["judged_cases"] += 1
            interaction_metrics[interaction_mode]["passed_cases"] += int(
                bool(behavior_pass)
            )
        if case["critical"] and judgment is not None and behavior_evaluated:
            critical_evaluated += 1
            critical_failures += int(judgment["critical_failure"] or response_error)

        usage = response.get("usage", {})
        input_tokens += usage.get("input_tokens", 0)
        output_tokens += usage.get("output_tokens", 0)
        latency_ms += response.get("latency_ms", 0)
        cost_usd += response.get("cost_usd", 0.0)
        result = {
            "case_id": case_id,
            "skill": case["skill"],
            "routing_outcome": outcome,
            "route_match": route_match,
            "behavior_pass": behavior_pass,
            "behavior_evaluated": behavior_evaluated,
            "expected_met": met,
            "expected_total": expected_total,
            "forbidden_violations": violations,
            "critical_failure": judgment["critical_failure"]
            if judgment is not None
            else False,
            "response_error": response_error,
        }
        if behavior_evaluated:
            result["interaction_mode"] = case.get("interaction_mode", "deliver")
        validate_instance(
            contract_validator(run_schema, "caseResult"),
            result,
            label=f"result[{case_id}]",
        )
        case_results.append(result)

    total = len(cases)
    metrics = {
        "schema_version": 1,
        "suite_sha256": manifest["suite_sha256"],
        "runtime": manifest["runtime"],
        "model": manifest["model"],
        "condition": manifest["condition"],
        "judge": judgment_set["judge"],
        "coverage": {
            "cases": total,
            "responses": len(responses),
            "judgments": len(judgments),
        },
        "routing": {
            **counts,
            "precision": ratio(counts["tp"], counts["tp"] + counts["fp"]),
            "recall": ratio(counts["tp"], counts["tp"] + counts["fn"]),
            "accuracy": ratio(counts["tp"] + counts["tn"], total),
            "route_accuracy": ratio(route_matches, total),
        },
        "behavior": {
            "passed_cases": behavior_passes,
            "judged_cases": len(behavior_cases),
            "pass_rate": ratio(behavior_passes, len(behavior_cases)),
            "criteria_met": criteria_met,
            "criteria_total": criteria_total,
            "forbidden_violations": forbidden_violations,
            "by_interaction_mode": {
                mode: {
                    **counts,
                    "pass_rate": ratio(counts["passed_cases"], counts["judged_cases"]),
                }
                for mode, counts in interaction_metrics.items()
            },
        },
        "critical": {
            "evaluated_cases": critical_evaluated,
            "failures": critical_failures,
            "failure_rate": ratio(critical_failures, critical_evaluated),
            "zero_failure_gate_pass": critical_evaluated > 0 and critical_failures == 0,
            "zero_failure_upper_bound_95": zero_failure_upper_bound_95(
                critical_evaluated, critical_failures
            ),
            "upper_bound_method": "exact-clopper-pearson-zero-failure",
        },
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "cost_usd": cost_usd,
        },
    }
    validate_instance(
        contract_validator(run_schema, "results"), metrics, label="metrics"
    )
    results_dir = run_dir / "results"
    write_immutable(results_dir / "cases.jsonl", jsonl_text(case_results), force=force)
    metrics_path = results_dir / "metrics.json"
    write_immutable(metrics_path, pretty_json(metrics), force=force)
    return metrics_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare, compose, ingest, and score deterministic "
            "GeoAI Skills evaluations."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Create a blind request manifest")
    prepare.add_argument("--runtime", required=True, help="Agent runtime name")
    prepare.add_argument("--model", required=True, help="Model identifier")
    prepare.add_argument(
        "--condition",
        required=True,
        choices=("skills-enabled", "skills-disabled"),
    )
    prepare.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    prepare.add_argument("--run-id", help="Optional stable run directory name")
    prepare.add_argument(
        "--scope",
        dest="evaluation_scope",
        choices=("routing", "behavior", "all"),
        default="all",
        help="Select all routing cases, only behavior-evaluable cases, or the combined suite",
    )
    prepare.add_argument(
        "--split",
        choices=VALID_SPLITS,
        default="all",
        help=(
            "Restrict the run to one half of evals/split.json. Use 'dev' while "
            "iterating; 'holdout' only for a release candidate."
        ),
    )

    compose = subparsers.add_parser(
        "compose",
        help="Build a complete batch from a primary run and explicit retries",
    )
    compose.add_argument("--run-dir", type=Path, required=True)
    compose.add_argument("--primary-run", type=Path, required=True)
    compose.add_argument(
        "--replacement-run",
        type=Path,
        action="append",
        default=[],
        dest="replacement_runs",
        help="Run whose response rows explicitly replace primary rows; repeat as needed",
    )
    compose.add_argument(
        "--replacement-case-id",
        action="append",
        default=None,
        dest="replacement_case_ids",
        help=(
            "Select a case from the replacement runs; repeat for mixed-scope "
            "retry batches. Without this option every replacement row is selected."
        ),
    )
    compose.add_argument(
        "--response-relative-path",
        type=Path,
        default=Path("adapter/claude-code.responses.jsonl"),
        help="Response JSONL path relative to every source run",
    )
    compose.add_argument(
        "--force", action="store_true", help="Replace different composed content"
    )

    ingest = subparsers.add_parser(
        "ingest", help="Validate and cache raw runtime responses"
    )
    ingest.add_argument("--run-dir", type=Path, required=True)
    ingest.add_argument("--input", type=Path, required=True, dest="input_path")
    ingest.add_argument(
        "--force", action="store_true", help="Replace different cached content"
    )

    score = subparsers.add_parser(
        "score", help="Score cached responses from explicit judgments"
    )
    score.add_argument("--run-dir", type=Path, required=True)
    score.add_argument("--judgments", type=Path, required=True, dest="judgments_path")
    score.add_argument(
        "--routing-only",
        action="store_true",
        help="Score routing without behavior judgments, including legacy combined runs",
    )
    score.add_argument(
        "--force", action="store_true", help="Replace different result content"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            output = prepare_run(
                runtime=args.runtime,
                model=args.model,
                condition=args.condition,
                evaluation_scope=args.evaluation_scope,
                split=args.split,
                runs_dir=args.runs_dir,
                run_id=args.run_id,
            )
        elif args.command == "compose":
            output = compose_responses(
                run_dir=args.run_dir,
                primary_run=args.primary_run,
                replacement_runs=args.replacement_runs,
                replacement_case_ids=args.replacement_case_ids,
                response_relative_path=args.response_relative_path,
                force=args.force,
            )
        elif args.command == "ingest":
            output = ingest_responses(
                run_dir=args.run_dir,
                input_path=args.input_path,
                force=args.force,
            )
        else:
            output = score_run(
                run_dir=args.run_dir,
                judgments_path=args.judgments_path,
                routing_only=args.routing_only,
                force=args.force,
            )
    except (EvalRunnerError, OSError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
