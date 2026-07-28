"""Tests for deterministic repository-local Markdown link validation."""

from __future__ import annotations

from pathlib import Path

from tools import check_links

ROOT = Path(__file__).resolve().parent.parent


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def reasons(root: Path) -> list[str]:
    return [issue.reason for issue in check_links.check_repository(root).issues]


def test_committed_tree_has_no_broken_internal_links() -> None:
    assert check_links.check_repository(ROOT).issues == ()


def test_valid_relative_files_images_and_anchors_pass(tmp_path: Path) -> None:
    write(
        tmp_path / "README.md",
        "\n".join(
            [
                "[Guide](docs/guide.md#quick-start)",
                "![Preview](assets/preview.png)",
                "[Same file](#overview)",
                "",
                "## Overview",
            ]
        ),
    )
    write(tmp_path / "docs" / "guide.md", "# Quick start\n")
    write(tmp_path / "assets" / "preview.png", "not a real image")

    report = check_links.check_repository(tmp_path)

    assert report.internal_links == 3
    assert report.issues == ()


def test_missing_target_fails(tmp_path: Path) -> None:
    write(tmp_path / "README.md", "[Missing](docs/missing.md)\n")

    assert reasons(tmp_path) == ["target does not exist"]


def test_missing_markdown_anchor_fails(tmp_path: Path) -> None:
    write(tmp_path / "README.md", "[Section](guide.md#absent)\n")
    write(tmp_path / "guide.md", "# Present\n")

    assert reasons(tmp_path) == ["Markdown anchor #absent does not exist"]


def test_exact_path_case_is_enforced_on_every_platform(tmp_path: Path) -> None:
    write(tmp_path / "README.md", "[Guide](docs/guide.md)\n")
    write(tmp_path / "docs" / "Guide.md", "# Guide\n")

    assert reasons(tmp_path) == ["path case mismatch; repository contains 'Guide.md'"]


def test_repository_escape_fails_closed(tmp_path: Path) -> None:
    write(tmp_path / "README.md", "[Outside](../outside.md)\n")

    assert reasons(tmp_path) == ["target escapes repository root"]


def test_external_links_and_code_examples_are_ignored(tmp_path: Path) -> None:
    write(
        tmp_path / "README.md",
        "\n".join(
            [
                "[Web](https://example.com/docs)",
                "[Mail](mailto:maintainer@example.com)",
                "`[Inline example](missing-inline.md)`",
                "```markdown",
                "[Fenced example](missing-fenced.md)",
                "```",
            ]
        ),
    )

    report = check_links.check_repository(tmp_path)

    assert report.internal_links == 0
    assert report.issues == ()


def test_duplicate_headings_receive_github_style_suffixes(tmp_path: Path) -> None:
    write(tmp_path / "README.md", "[Second](guide.md#repeat-1)\n")
    write(tmp_path / "guide.md", "# Repeat\n\n## Repeat\n")

    assert check_links.check_repository(tmp_path).issues == ()
