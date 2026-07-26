"""Regression tests for the 2026-07-26 security audit fixes.

Three unrelated hardening changes, each pinned here so the reason survives the
change:

* artifact capture is bounded — the model controls artifact size;
* provider error bodies are redacted before reaching a trace on disk;
* a fixture may declare its own sha256, making a content swap visible in review.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.adapters.claude_code import (
    MAX_ARTIFACT_BYTES,
    MAX_ARTIFACT_PREVIEW_CHARS,
    capture_artifacts,
    hash_file,
)
from tools.adapters.gemini_api import redact_secrets
from tools.eval_runner import EvalRunnerError, normalize_fixture

# Secret scanners match on the literal shape of a Google key, so these fixtures
# are assembled at runtime rather than written out. GitHub flagged the earlier
# literal as a public leak — a false positive, but one that trains people to
# ignore the alert, which is the real cost.
_FAKE_PREFIX = "AI" + "za"


def fake_google_key(tail: str) -> str:
    """Return a 39-character string shaped like a Google key but never one."""
    body = tail.ljust(35, "0")[:35]
    return _FAKE_PREFIX + body


HYPHEN_KEY = fake_google_key("SyB1234567890abcdefghijklmnopqrst-")
UNDERSCORE_KEY = fake_google_key("SyB1234567890abcdefghijklmnopqrst_")
PLAIN_KEY = fake_google_key("A" * 35)


# --- bounded artifact capture -------------------------------------------


def a_case(path: str = "outputs/report.md", media_type: str = "text/markdown") -> dict:
    return {
        "expected_artifacts": [{"path": path, "media_type": media_type}],
    }


def test_a_small_text_artifact_is_captured_whole(tmp_path: Path) -> None:
    target = tmp_path / "outputs" / "report.md"
    target.parent.mkdir(parents=True)
    target.write_text("# Review\nfindings", encoding="utf-8")

    artifact = capture_artifacts(a_case(), tmp_path)[0]

    assert artifact["text_preview"] == "# Review\nfindings"
    assert artifact["preview_truncated"] is False
    assert artifact["size_bytes"] == len("# Review\nfindings")


def test_a_long_text_artifact_is_truncated_at_the_preview_window(tmp_path: Path) -> None:
    target = tmp_path / "outputs" / "report.md"
    target.parent.mkdir(parents=True)
    target.write_text("x" * (MAX_ARTIFACT_PREVIEW_CHARS + 500), encoding="utf-8")

    artifact = capture_artifacts(a_case(), tmp_path)[0]

    assert len(artifact["text_preview"]) == MAX_ARTIFACT_PREVIEW_CHARS
    assert artifact["preview_truncated"] is True


def test_an_oversized_artifact_is_recorded_but_never_loaded(tmp_path: Path) -> None:
    """The failure this guards: a model-controlled write exhausting memory.

    The row must still exist — a missing artifact and an oversized one are
    different facts about the run, and collapsing them would hide the second.
    """
    target = tmp_path / "outputs" / "report.md"
    target.parent.mkdir(parents=True)
    with target.open("wb") as handle:
        handle.truncate(MAX_ARTIFACT_BYTES + 1)

    artifact = capture_artifacts(a_case(), tmp_path)[0]

    assert artifact["oversized"] is True
    assert artifact["size_limit_bytes"] == MAX_ARTIFACT_BYTES
    assert "text_preview" not in artifact
    assert artifact["sha256"]


def test_a_binary_artifact_gets_no_preview(tmp_path: Path) -> None:
    target = tmp_path / "outputs" / "map.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    artifact = capture_artifacts(a_case("outputs/map.png", "image/png"), tmp_path)[0]

    assert "text_preview" not in artifact
    assert artifact["size_bytes"] == 72


def test_a_missing_artifact_produces_no_row(tmp_path: Path) -> None:
    assert capture_artifacts(a_case(), tmp_path) == []


def test_streamed_hash_matches_a_whole_file_hash(tmp_path: Path) -> None:
    import hashlib

    target = tmp_path / "blob.bin"
    payload = bytes(range(256)) * 8192
    target.write_bytes(payload)

    assert hash_file(target, chunk_bytes=1024) == hashlib.sha256(payload).hexdigest()


def test_multibyte_text_is_not_cut_mid_character(tmp_path: Path) -> None:
    """Truncation happens on characters, not bytes, so Turkish text survives."""
    target = tmp_path / "outputs" / "report.md"
    target.parent.mkdir(parents=True)
    target.write_text("ğüşiöç" * 10, encoding="utf-8")

    artifact = capture_artifacts(a_case(), tmp_path)[0]

    assert artifact["text_preview"] == "ğüşiöç" * 10
    assert "�" not in artifact["text_preview"]


# --- trace redaction -----------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        f"x-goog-api-key: {HYPHEN_KEY}",
        f"https://example.com/v1?key={HYPHEN_KEY}",
        f'api_key="{HYPHEN_KEY}"',
        "Authorization: Bearer abc.def.ghi",
    ],
)
def test_credential_shaped_text_is_masked(raw: str) -> None:
    redacted = redact_secrets(raw)

    assert "[REDACTED]" in redacted
    assert HYPHEN_KEY not in redacted


@pytest.mark.parametrize(
    "key",
    [
        PLAIN_KEY,
        HYPHEN_KEY,  # ends in a hyphen
        UNDERSCORE_KEY,  # ends in an underscore
    ],
)
def test_a_bare_google_key_is_masked_even_without_a_label(key: str) -> None:
    """A key ending in `-` or `_` defeated an earlier `\\b`-anchored pattern."""
    assert len(key) == 39
    assert "AIza" not in redact_secrets(f"leaked {key} here")


def test_ordinary_error_text_is_left_alone() -> None:
    """Over-redaction would destroy the diagnostic value of the trace."""
    message = "Gemini blocked the prompt: SAFETY (candidate 1 of 1)"

    assert redact_secrets(message) == message


def test_redaction_is_idempotent() -> None:
    once = redact_secrets("x-goog-api-key: abc123")

    assert redact_secrets(once) == once


# --- declared fixture hash ----------------------------------------------


def a_fixture_dir(tmp_path: Path, content: bytes = b"payload") -> tuple[Path, str]:
    import hashlib

    fixtures = tmp_path / "evals" / "fixtures" / "case"
    fixtures.mkdir(parents=True)
    (fixtures / "input.json").write_bytes(content)
    return tmp_path / "evals", hashlib.sha256(content).hexdigest()


def test_a_fixture_without_a_declared_hash_still_loads(tmp_path: Path) -> None:
    eval_dir, digest = a_fixture_dir(tmp_path)

    normalized = normalize_fixture(
        eval_dir,
        {"source": "fixtures/case/input.json", "workspace_path": "inputs/input.json"},
        repository_root=tmp_path,
    )

    assert normalized["sha256"] == digest


def test_a_matching_declared_hash_is_accepted(tmp_path: Path) -> None:
    eval_dir, digest = a_fixture_dir(tmp_path)

    normalized = normalize_fixture(
        eval_dir,
        {
            "source": "fixtures/case/input.json",
            "workspace_path": "inputs/input.json",
            "sha256": digest,
        },
        repository_root=tmp_path,
    )

    assert normalized["sha256"] == digest


def test_a_mismatched_declared_hash_is_refused(tmp_path: Path) -> None:
    """A pull request that swaps fixture bytes must also change this line."""
    eval_dir, _ = a_fixture_dir(tmp_path)

    with pytest.raises(EvalRunnerError, match="does not match the declared sha256"):
        normalize_fixture(
            eval_dir,
            {
                "source": "fixtures/case/input.json",
                "workspace_path": "inputs/input.json",
                "sha256": "0" * 64,
            },
            repository_root=tmp_path,
        )


def test_the_schema_accepts_a_declared_fixture_hash() -> None:
    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "evals" / "schema.json").read_text(
            encoding="utf-8"
        )
    )
    fixture_props = (
        schema["properties"]["evals"]["items"]["properties"]["fixtures"]["items"][
            "properties"
        ]
    )

    assert fixture_props["sha256"]["pattern"] == "^[a-f0-9]{64}$"