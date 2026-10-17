"""Release gate; no core edits, baseline regeneration or automatic repair."""

from pathlib import Path
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[2]
COMMANDS = [
    ["agent-kit/geoai_agents.py", "verify-base", "--root", "."],
    ["tools/build_runtime_hash_registry.py", "--check"],
    ["tools/check_regression_gates.py"],
    ["agent-kit/geoai_agents.py", "render", "--check"],
    ["agent-kit/geoai_agents.py", "evaluate-pilots"],
    ["-m", "pytest", "agent-kit/tests", "-q", "-p", "no:cacheprovider"],
    ["-m", "ruff", "check", "agent-kit"],
]


def main():
    artifacts = REPO / "agent-kit/artifacts"
    artifacts.mkdir(exist_ok=True)
    # A unique owned directory avoids shared pytest-temp ACLs and deleting old runs.
    scratch = Path(tempfile.mkdtemp(prefix="validation-", dir=artifacts)) / "pytest"
    for command in COMMANDS:
        if command[:2] == ["-m", "pytest"]:
            command = [*command, "--basetemp", str(scratch)]
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, *command], cwd=REPO, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
