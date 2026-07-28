"""Deterministic repository-local Markdown link validation.

External URLs are deliberately out of scope here: transient network failures
must not make an otherwise valid pull request unmergeable. This gate checks the
part the repository controls — relative targets, exact path casing, repository
boundaries, and Markdown heading anchors.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent

IGNORED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "evals/runs",
    "venv",
}
EXTERNAL_SCHEMES = {"data", "http", "https", "mailto", "tel"}
FENCE_PATTERN = re.compile(r"^\s*(`{3,}|~{3,})")
HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
HTML_ID_PATTERN = re.compile(r"""<(?:a|[A-Za-z][\w:-]*)\b[^>]*\bid=["']([^"']+)["']""")
INLINE_CODE_PATTERN = re.compile(r"(`+)(.+?)\1")
INLINE_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^)]+\)")


@dataclass(frozen=True, order=True)
class LinkIssue:
    source: Path
    line: int
    target: str
    reason: str

    def render(self, root: Path) -> str:
        source = self.source.relative_to(root).as_posix()
        return f"{source}:{self.line}: {self.reason}: {self.target!r}"


@dataclass(frozen=True)
class LinkReport:
    markdown_files: int
    internal_links: int
    issues: tuple[LinkIssue, ...]


def _is_ignored(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    parts = relative.parts
    for ignored in IGNORED_DIRECTORIES:
        ignored_parts = tuple(ignored.split("/"))
        if any(
            parts[index : index + len(ignored_parts)] == ignored_parts
            for index in range(len(parts))
        ):
            return True
    return False


def markdown_files(root: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in root.rglob("*.md")
            if path.is_file() and not _is_ignored(path, root)
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def _mask_inline_code(line: str) -> str:
    return INLINE_CODE_PATTERN.sub(lambda match: " " * len(match.group(0)), line)


def iter_inline_links(text: str) -> list[tuple[int, str]]:
    """Return one-line inline Markdown link targets outside fenced/code spans."""

    links: list[tuple[int, str]] = []
    fence: str | None = None

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        fence_match = FENCE_PATTERN.match(raw_line)
        if fence_match:
            marker = fence_match.group(1)
            marker_type = marker[0]
            if fence is None:
                fence = marker_type
            elif fence == marker_type:
                fence = None
            continue
        if fence is not None:
            continue

        line = _mask_inline_code(raw_line)
        cursor = 0
        while True:
            marker = line.find("](", cursor)
            if marker < 0:
                break
            if line.rfind("[", 0, marker) < 0:
                cursor = marker + 2
                continue

            index = marker + 2
            while index < len(line) and line[index].isspace():
                index += 1
            if index >= len(line):
                break

            if line[index] == "<":
                end = line.find(">", index + 1)
                if end < 0:
                    cursor = index + 1
                    continue
                target = raw_line[index + 1 : end]
                cursor = end + 1
            else:
                start = index
                depth = 0
                escaped = False
                while index < len(line):
                    character = line[index]
                    if escaped:
                        escaped = False
                    elif character == "\\":
                        escaped = True
                    elif character == "(":
                        depth += 1
                    elif character == ")":
                        if depth == 0:
                            break
                        depth -= 1
                    elif character.isspace() and depth == 0:
                        break
                    index += 1
                target = raw_line[start:index]
                cursor = max(index + 1, marker + 2)

            if target:
                links.append((line_number, target.replace("\\(", "(").replace("\\)", ")")))

    return links


def github_slug(heading: str) -> str:
    """Approximate GitHub's documented heading-ID behavior for repository prose."""

    heading = INLINE_LINK_PATTERN.sub(r"\1", heading)
    heading = re.sub(r"<[^>]+>", "", heading)
    heading = heading.replace("`", "").casefold()
    heading = re.sub(r"[^\w\- ]", "", heading, flags=re.UNICODE)
    return re.sub(r"\s+", "-", heading.strip())


def heading_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    text = path.read_text(encoding="utf-8-sig")
    fence: str | None = None

    for line in text.splitlines():
        fence_match = FENCE_PATTERN.match(line)
        if fence_match:
            marker_type = fence_match.group(1)[0]
            if fence is None:
                fence = marker_type
            elif fence == marker_type:
                fence = None
            continue
        if fence is not None:
            continue

        for explicit_id in HTML_ID_PATTERN.findall(line):
            anchors.add(explicit_id.casefold())

        heading_match = HEADING_PATTERN.match(line)
        if not heading_match:
            continue
        base = github_slug(heading_match.group(1))
        if not base:
            continue
        duplicate_index = seen.get(base, 0)
        anchor = base if duplicate_index == 0 else f"{base}-{duplicate_index}"
        seen[base] = duplicate_index + 1
        anchors.add(anchor)

    return anchors


def _normalised_parts(source: Path, target_path: str, root: Path) -> tuple[str, ...] | None:
    if target_path.startswith("/"):
        parts: list[str] = []
    else:
        parts = list(source.parent.relative_to(root).parts)

    for part in unquote(target_path).replace("\\", "/").split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    return tuple(parts)


def _exact_path(root: Path, parts: tuple[str, ...]) -> tuple[Path | None, str | None]:
    current = root
    for part in parts:
        if not current.is_dir():
            return None, "parent target is not a directory"
        names = {entry.name for entry in current.iterdir()}
        if part not in names:
            case_match = next((name for name in names if name.casefold() == part.casefold()), None)
            if case_match is not None:
                return None, f"path case mismatch; repository contains {case_match!r}"
            return None, "target does not exist"
        current = current / part
    return current, None


def _check_target(
    *,
    root: Path,
    source: Path,
    line: int,
    raw_target: str,
) -> LinkIssue | None:
    target = raw_target.strip()
    parsed = urlsplit(target)
    if parsed.scheme.casefold() in EXTERNAL_SCHEMES or target.startswith("//"):
        return None
    if parsed.scheme or parsed.netloc:
        return LinkIssue(source, line, raw_target, "unsupported non-local link scheme")

    if parsed.path:
        parts = _normalised_parts(source, parsed.path, root)
        if parts is None:
            return LinkIssue(source, line, raw_target, "target escapes repository root")

        target_file, path_error = _exact_path(root, parts)
        if path_error is not None:
            return LinkIssue(source, line, raw_target, path_error)
        if target_file is None:
            return LinkIssue(source, line, raw_target, "target could not be resolved")
    else:
        target_file = source

    fragment = unquote(parsed.fragment).casefold()
    if not fragment:
        return None
    if not target_file.is_file() or target_file.suffix.casefold() != ".md":
        return LinkIssue(source, line, raw_target, "anchor target is not a Markdown file")
    if fragment not in heading_anchors(target_file):
        return LinkIssue(source, line, raw_target, f"Markdown anchor #{fragment} does not exist")
    return None


def check_repository(root: Path = ROOT) -> LinkReport:
    root = root.resolve()
    files = markdown_files(root)
    issues: list[LinkIssue] = []
    internal_links = 0

    for source in files:
        text = source.read_text(encoding="utf-8-sig")
        for line, target in iter_inline_links(text):
            parsed = urlsplit(target)
            if parsed.scheme.casefold() in EXTERNAL_SCHEMES or target.startswith("//"):
                continue
            internal_links += 1
            issue = _check_target(root=root, source=source, line=line, raw_target=target)
            if issue is not None:
                issues.append(issue)

    return LinkReport(
        markdown_files=len(files),
        internal_links=internal_links,
        issues=tuple(sorted(issues)),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate repository-local Markdown paths and heading anchors."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="repository root to scan (defaults to the current project)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = check_repository(args.root)
    if report.issues:
        for issue in report.issues:
            print(issue.render(args.root.resolve()))
        print(
            f"\nlink check failed — {len(report.issues)} issue(s) across "
            f"{report.markdown_files} Markdown files"
        )
        return 1

    print(
        f"link check: pass — {report.internal_links} internal links across "
        f"{report.markdown_files} Markdown files"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
