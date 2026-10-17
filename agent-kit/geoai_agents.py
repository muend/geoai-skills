"""Repository and distribution entry point; does not require installing this package."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "runtime"))

from geoai_agents.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
