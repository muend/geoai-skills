"""Opt-in, bounded native runtime smoke; never a comparative benchmark result."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "runtime"))
from geoai_agents.core import file_hash, json_bytes, write_new  # noqa: E402
from geoai_agents.distribution import install  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", choices=("codex", "claude"), required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--skills-root", type=Path, required=True)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--timeout", type=int, default=480, choices=range(30, 901))
    args = parser.parse_args()
    args.destination = args.destination.resolve()
    args.skills_root = args.skills_root.resolve()
    if args.destination.exists():
        raise ValueError("smoke destination must be new")
    executable = shutil.which(args.runtime)
    if not executable:
        raise ValueError("native runtime executable unavailable")
    print(json.dumps({"runtime": args.runtime, "destination": str(args.destination),
                      "will_call_model": args.run, "timeout_seconds": args.timeout,
                      "benchmark_eligible": False}))
    if not args.run:
        return 0
    workspace = args.destination / "workspace"
    result = install(workspace, args.skills_root, args.runtime, apply=True)
    if result["exit_code"]:
        raise ValueError("incompatible base or installation conflict")
    task = {"schema_version": 1, "kind": "task", "task_id": "smoke-legend",
            "objective": "Explain an explicitly declared line-width legend to a new map reader",
            "audience": "non-specialist", "task_type": "explanation",
            "skills": ["cartography-geoviz"], "uses_data": False, "physical_claim": False,
            "user_facing_visual": False, "outputs": ["summary.txt"],
            "required_checks": ["legend-semantics"]}
    write_new(workspace / "task.json", json_bytes(task))
    write_new(workspace / "legend.txt", b"Stroke width represents observed pedestrian volume. "
              b"It does not establish physical access, safety, or path width.\n")
    prompt = """Implement this small GeoAI addon smoke in the current workspace only.
Read .geoai-agent-kit/START.md, installation.json, and task.json. The main session
is coordinator. Explicitly use the installed native geoai-specialist subagent
to read legend.txt and write summary.txt (three plain sentences) and artifacts.json.
Then explicitly use a separate native geoai-presentation-reviewer subagent to read
the original legend and summary and write review.json using records.schema.json.
Pass original files, not producer reasoning. Record actual distinct identities.
Each reviewer check cites local hash-bound files; evidence_files can be empty if
it cites only an artifact. No other roles or nested teams. Run the addon deliver
command and save its JSON as delivery.json. Return the actual delegation identities
and outcome. If native delegation, skills or tools are unavailable, say ABSTAIN
and stop; do not simulate separate agents. Do not alter installed files or skills.
This is a bounded smoke, not a benchmark or field-verification claim. No network
tools, other apps, publication, global edits, or installation are needed.
"""
    write_new(workspace / "REQUEST.txt", prompt.encode())
    if args.runtime == "codex":
        command = [executable, "exec", "--json", "--ephemeral", "--skip-git-repo-check",
                   "--ignore-user-config", "-s", "workspace-write", "-C", str(workspace),
                   "-o", str(args.destination / "final.txt"), "-"]
    else:
        command = [executable, "-p", "--output-format", "stream-json", "--verbose",
                   "--forward-subagent-text", "--no-session-persistence", "--max-turns", "24",
                   "--setting-sources", "project", "--strict-mcp-config",
                   "--allowedTools", "Read,Write,Edit,Bash(python *),Agent,Skill", "--tools",
                   "Read,Write,Edit,Bash,Agent,Skill"]
    started = time.monotonic()
    status, returncode = "error", None
    with (args.destination / "trace.log").open("wb") as stdout, (
            args.destination / "stderr.log").open("wb") as stderr:
        try:
            child = subprocess.run(  # noqa: S603 - explicit native executable and argv
                command, input=prompt.encode(), stdout=stdout, stderr=stderr,
                cwd=workspace, timeout=args.timeout, check=False)
            returncode = child.returncode
            status = "returned" if returncode == 0 else "error"
        except subprocess.TimeoutExpired:
            status = "interrupted"
    report = {"schema_version": 1, "kind": "native-smoke", "runtime": args.runtime,
              "process_status": status, "returncode": returncode,
              "latency_seconds": time.monotonic() - started,
              "trace_sha256": file_hash(args.destination / "trace.log"),
              "benchmark_eligible": False,
              "reason": "Default account/profile smoke; loaded customization isolation unproven",
              "delivery_record_exists": (workspace / "delivery.json").is_file()}
    write_new(args.destination / "smoke.json", json_bytes(report))
    print(json.dumps(report))
    return 0 if status == "returned" and report["delivery_record_exists"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
