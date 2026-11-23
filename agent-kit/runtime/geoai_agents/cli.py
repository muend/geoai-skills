"""CLI for the optional addon. Defaults never mutate installed agent definitions."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .checks import run_check
from .core import contained, json_bytes, read_json, write_new
from .distribution import build, install, legacy_root, render
from .evaluation import compare, evaluate_pilots, prepare, verify_environment
from .integrity import verify_base, verify_package
from .workflow import delivery, plan, validate_record


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="GeoAI Agents: optional, frozen-core addon")
    sub = p.add_subparsers(dest="command", required=True)
    for command in ("verify-base", "verify-skills"):
        q = sub.add_parser(command)
        q.add_argument("--root", type=Path, required=True)
    q = sub.add_parser("render")
    q.add_argument("--check", action="store_true")
    for command in ("plan", "validate-record"):
        q = sub.add_parser(command)
        q.add_argument("record", type=Path)
    q = sub.add_parser("check")
    q.add_argument("name")
    q.add_argument("--root", type=Path, required=True)
    q.add_argument("--spec", type=Path, required=True)
    q = sub.add_parser("legacy")
    q.add_argument("args", nargs=argparse.REMAINDER)
    q = sub.add_parser("deliver")
    q.add_argument("--task", type=Path, required=True)
    q.add_argument("--artifacts", type=Path, required=True)
    q.add_argument("--review", type=Path, action="append", default=[])
    q.add_argument("--root", type=Path, required=True)
    q.add_argument("--repairs", type=int, choices=range(3), default=0)
    q = sub.add_parser("install")
    q.add_argument("--target", type=Path, required=True)
    q.add_argument("--skills-root", type=Path, required=True)
    q.add_argument("--runtime", choices=("codex", "claude"), required=True)
    q.add_argument("--apply", action="store_true")
    q = sub.add_parser("build")
    q.add_argument("--output", type=Path, required=True)
    q = sub.add_parser("verify-package")
    q.add_argument("--root", type=Path, required=True)
    q = sub.add_parser("evaluate-pilots")
    q.add_argument("--output", type=Path)
    q = sub.add_parser("prepare-evaluation")
    q.add_argument("--destination", type=Path, required=True)
    q.add_argument("--skills-root", type=Path, required=True)
    q.add_argument("--runtime", choices=("codex", "claude"), required=True)
    q = sub.add_parser("verify-environment")
    q.add_argument("--root", type=Path, required=True)
    q = sub.add_parser("compare")
    q.add_argument("--environment", type=Path, action="append", required=True)
    q.add_argument("--run", type=Path, action="append", required=True)
    q = sub.add_parser("record-failure")
    q.add_argument("--record", type=Path, required=True)
    q.add_argument("--directory", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command in {"verify-base", "verify-skills"}:
            result = verify_base(args.root, skills_only=args.command == "verify-skills")
        elif args.command == "render":
            changed = render(check=args.check)
            result = {"changed": changed, "exit_code": 1 if args.check and changed else 0}
        elif args.command == "plan":
            result = plan(read_json(args.record))
        elif args.command == "validate-record":
            validate_record(read_json(args.record))
            result = {"exit_code": 0, "valid": True}
        elif args.command == "check":
            result = run_check(args.name, args.root, read_json(args.spec))
        elif args.command == "legacy":
            root = legacy_root()
            forwarded = args.args[1:] if args.args[:1] == ["--"] else args.args
            completed = subprocess.run(  # noqa: S603 - fixed executable/module, argv only
                [sys.executable, "-m", "tools.verify", *forwarded], cwd=root,
                check=False, timeout=60)
            return completed.returncode
        elif args.command == "deliver":
            result = delivery(read_json(args.task), read_json(args.artifacts),
                              [read_json(p) for p in args.review], args.root, args.repairs)
        elif args.command == "install":
            result = install(args.target, args.skills_root, args.runtime, apply=args.apply)
        elif args.command == "build":
            manifest = build(args.output)
            result = {"exit_code": 0, "archive": str(args.output),
                      "agent_runtime_sha256": manifest["agent_runtime_sha256"]}
        elif args.command == "verify-package":
            result = verify_package(args.root)
        elif args.command == "evaluate-pilots":
            result = evaluate_pilots()
            if args.output:
                write_new(args.output, json_bytes(result))
        elif args.command == "prepare-evaluation":
            result = prepare(args.destination, args.skills_root, args.runtime)
        elif args.command == "verify-environment":
            result = verify_environment(args.root)
        elif args.command == "compare":
            environments = []
            for environment_path in args.environment:
                environment = read_json(environment_path)
                if verify_environment(environment_path.parent)["exit_code"]:
                    environment["isolation_issues"] = ["workspace changed or contaminated"]
                environments.append(environment)
            result = compare(environments,
                             [read_json(p) for p in args.run], [p.parent for p in args.run])
        elif args.command == "record-failure":
            record = read_json(args.record)
            validate_record(record)
            if record["kind"] != "failure":
                raise ValueError("expected failure record")
            path = contained(args.directory, record["task_id"] + ".json")
            write_new(path, json_bytes(record))
            result = {"exit_code": 0, "path": str(path), "core_changed": False}
        else:
            raise ValueError("unsupported command")
        print(json_bytes(result).decode("utf-8"), end="")
        return result.get("exit_code", 0)
    except (OSError, ValueError, TypeError, KeyError, ImportError,
            subprocess.TimeoutExpired) as exc:
        print(json.dumps({"exit_code": 2, "outcome": "abstain", "error": str(exc)},
                         ensure_ascii=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
