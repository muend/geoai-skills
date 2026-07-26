"""Record where the data came from, or refuse to call the result reproducible.

Measured behaviour: the criterion "Records source, query parameters, retrieval
date, and provenance manifest" scored 0% coverage. The model reaches for the
data and never writes down what it reached for. Six months later nobody can
tell which OSM extract, which Sentinel processing baseline, or which API
revision produced the figure.

This module makes provenance an artifact rather than an intention: build a
manifest, hash it, and verify completeness. The hash is over the normalised
manifest, so two runs that used genuinely identical inputs produce the same
identifier and two that did not, do not.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, UTC
from typing import Any

from .result import Result, failed, passed

CHECK = "provenance.manifest"

REQUIRED_FIELDS = ("name", "source", "retrieved_at")
RECOMMENDED_FIELDS = ("query", "version", "licence", "spatial_extent", "crs")


def _isoformat(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


@dataclass
class Source:
    """One input dataset and everything needed to fetch it again."""

    name: str
    source: str
    retrieved_at: datetime | date | str
    query: str | None = None
    version: str | None = None
    licence: str | None = None
    spatial_extent: tuple[float, float, float, float] | None = None
    crs: str | None = None
    checksum: str | None = None
    notes: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "source": self.source,
            "retrieved_at": _isoformat(self.retrieved_at),
        }
        for key in ("query", "version", "licence", "crs", "checksum", "notes"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        if self.spatial_extent is not None:
            payload["spatial_extent"] = list(self.spatial_extent)
        if self.extra:
            payload["extra"] = dict(sorted(self.extra.items()))
        return payload

    def missing_required(self) -> list[str]:
        return [f for f in REQUIRED_FIELDS if not getattr(self, f, None)]

    def missing_recommended(self) -> list[str]:
        return [f for f in RECOMMENDED_FIELDS if not getattr(self, f, None)]


def build_manifest(
    sources: list[Source],
    *,
    analysis: str,
    produced_at: datetime | None = None,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble a manifest and stamp it with a content hash."""
    if not sources:
        raise ValueError("a provenance manifest with no sources records nothing")

    body = {
        "kind": "geoai-provenance-manifest",
        "schema_version": 1,
        "analysis": analysis,
        "produced_at": _isoformat(produced_at or datetime.now(UTC)),
        "parameters": dict(sorted((parameters or {}).items())),
        "sources": [s.to_dict() for s in sources],
    }
    digest_input = json.dumps(
        {k: v for k, v in body.items() if k != "produced_at"},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    body["content_sha256"] = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
    return body


def verify_manifest(manifest: dict[str, Any], *, strict: bool = False) -> Result:
    """Fail when a manifest cannot support reproduction.

    ``strict`` also demands the recommended fields. Off by default because a
    recommended field that is genuinely unknowable should be documented as
    unknown rather than faked, and this check cannot tell the difference.
    """
    if manifest.get("kind") != "geoai-provenance-manifest":
        return failed(CHECK, "not a provenance manifest", evidence=[repr(manifest.get("kind"))])

    sources = manifest.get("sources") or []
    if not sources:
        return failed(CHECK, "manifest declares no sources")

    problems: list[str] = []
    for index, entry in enumerate(sources):
        label = entry.get("name") or f"source[{index}]"
        for key in REQUIRED_FIELDS:
            if not entry.get(key):
                problems.append(f"{label}: missing required field {key!r}")
        if strict:
            for key in RECOMMENDED_FIELDS:
                if not entry.get(key):
                    problems.append(f"{label}: missing recommended field {key!r}")

    if not manifest.get("content_sha256"):
        problems.append("manifest carries no content_sha256")

    if problems:
        return failed(
            CHECK,
            f"{len(problems)} provenance gap(s); the result cannot be reproduced "
            f"from this manifest",
            evidence=problems,
            n_sources=len(sources),
        )

    return passed(
        CHECK,
        f"{len(sources)} source(s) fully recorded",
        n_sources=len(sources),
        content_sha256=manifest["content_sha256"],
    )


def diff_manifests(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    """Describe what changed between two runs, ignoring the timestamp.

    Useful when a figure changes and nobody knows why: this answers "did the
    inputs change, or did the code?".
    """
    if left.get("content_sha256") == right.get("content_sha256"):
        return []

    differences: list[str] = []
    left_sources = {s.get("name"): s for s in left.get("sources", [])}
    right_sources = {s.get("name"): s for s in right.get("sources", [])}

    for name in sorted(set(left_sources) - set(right_sources)):
        differences.append(f"source removed: {name}")
    for name in sorted(set(right_sources) - set(left_sources)):
        differences.append(f"source added: {name}")
    for name in sorted(set(left_sources) & set(right_sources)):
        a, b = left_sources[name], right_sources[name]
        for key in sorted(set(a) | set(b)):
            if a.get(key) != b.get(key):
                differences.append(f"{name}.{key}: {a.get(key)!r} -> {b.get(key)!r}")

    left_params = left.get("parameters", {})
    right_params = right.get("parameters", {})
    for key in sorted(set(left_params) | set(right_params)):
        if left_params.get(key) != right_params.get(key):
            differences.append(
                f"parameter {key}: {left_params.get(key)!r} -> {right_params.get(key)!r}"
            )

    return differences or ["manifests differ but no field-level change was found"]
