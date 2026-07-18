#!/usr/bin/env python3
"""Lint every skill in skills/ against the Agent Skills spec + repo rules.

Run from the repo root:  python tools/validate_skills.py
Exits non-zero on any error (warnings do not fail the build).

Checks per skill:
  E1  SKILL.md exists
  E2  YAML frontmatter parses and is the first thing in the file
  E3  required fields present: name, description
  E4  name is kebab-case, <= 64 chars, matches the folder name exactly
  E5  name does not contain "claude" or "anthropic"
  E6  description <= 1024 chars and >= 10 words
  E7  no '<' or '>' anywhere in frontmatter (spec security constraint)
  E8  every relative path referenced as scripts/... or references/... exists
  E9  agents/openai.yaml exists and contains valid interface metadata
  E10 OpenAI metadata lengths and $skill-name prompt reference are valid
  E11 execution contract declares workflow, decisions, verification,
      failure modes, and deliverables
  E12 authoritative source registry is linked and includes freshness metadata
  W1  description > 700 chars (session token overhead — consider trimming)
  W2  SKILL.md body > 500 lines (move material to references/)
  W3  no evals/evals.json (repo standard: 3+ scenarios per skill)
  W4  authoritative source registry is older than 400 days
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
REL_REF = re.compile(r"(?:^|[\s(`])((?:scripts|references|assets)/[\w\-./]+)")

errors: list[str] = []
warnings: list[str] = []


def err(skill: str, code: str, msg: str) -> None:
    errors.append(f"[{skill}] {code}: {msg}")


def warn(skill: str, code: str, msg: str) -> None:
    warnings.append(f"[{skill}] {code}: {msg}")


def split_frontmatter(text: str) -> tuple[dict | None, str]:
    if not text.startswith("---"):
        return None, text
    parts = text.split("\n---", 2)
    if len(parts) < 2:
        return None, text
    try:
        meta = yaml.safe_load(parts[0].lstrip("-").lstrip())
    except yaml.YAMLError:
        return None, text
    body = parts[1].split("\n", 1)[-1] if len(parts) > 1 else ""
    return (meta if isinstance(meta, dict) else None), body


def check_skill(folder: Path) -> None:
    name = folder.name
    md = folder / "SKILL.md"
    if not md.exists():
        err(name, "E1", "SKILL.md missing")
        return
    text = md.read_text(encoding="utf-8")
    meta, body = split_frontmatter(text)
    if meta is None:
        err(name, "E2", "frontmatter missing or not valid YAML")
        return

    fm_raw = text.split("\n---", 2)[0]
    if "<" in fm_raw or ">" in fm_raw.replace(">-", "").replace(">+", ""):
        # allow YAML block scalars '>-' / '>+'
        cleaned = re.sub(r">[-+]?\n", "", fm_raw)
        if "<" in cleaned or ">" in cleaned:
            err(name, "E7", "'<' or '>' found in frontmatter")

    for field in ("name", "description"):
        if not meta.get(field):
            err(name, "E3", f"required field '{field}' missing")
    n = str(meta.get("name", ""))
    if n:
        if n != name:
            err(name, "E4", f"frontmatter name '{n}' != folder name '{name}'")
        if len(n) > 64 or not KEBAB.match(n):
            err(name, "E4", f"name '{n}' not kebab-case or > 64 chars")
        if "claude" in n.lower() or "anthropic" in n.lower():
            err(name, "E5", "name must not contain 'claude'/'anthropic'")
    d = str(meta.get("description", ""))
    if d:
        if len(d) > 1024:
            err(name, "E6", f"description {len(d)} chars > 1024")
        elif len(d) > 700:
            warn(name, "W1", f"description {len(d)} chars (> 700; consider trimming)")
        if len(d.split()) < 10:
            err(name, "E6", "description under 10 words — too vague to trigger")

    lines = body.count("\n") + 1
    if lines > 500:
        warn(name, "W2", f"body {lines} lines (> 500; use references/)")

    contract_fields = (
        "## Execution contract",
        "**Workflow:**",
        "**Decision rules:**",
        "**Verification protocol:**",
        "**Failure modes:**",
        "**Deliverables:**",
    )
    for field in contract_fields:
        if field not in body:
            err(name, "E11", f"execution contract field missing: {field}")

    for m in REL_REF.finditer(body):
        rel = m.group(1).rstrip(".,)`:")
        if "." not in Path(rel).name:
            continue
        if (folder / rel).exists():
            continue
        # cross-skill reference (e.g. `other-skill` -> `references/x.md`):
        # accept if the path exists inside any sibling skill folder
        if any((sib / rel).exists() for sib in SKILLS.iterdir() if sib.is_dir()):
            continue
        err(name, "E8", f"referenced file does not exist: {rel}")

    ev = folder / "evals" / "evals.json"
    if not ev.exists():
        warn(name, "W3", "no evals/evals.json")
    else:
        try:
            data = json.loads(ev.read_text(encoding="utf-8"))
            if len(data.get("evals", [])) < 3:
                warn(name, "W3", "fewer than 3 eval scenarios")
        except json.JSONDecodeError:
            err(name, "E8", "evals/evals.json is not valid JSON")

    openai_yaml = folder / "agents" / "openai.yaml"
    if not openai_yaml.exists():
        err(name, "E9", "agents/openai.yaml missing")
        return
    try:
        openai_data = yaml.safe_load(openai_yaml.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        err(name, "E9", "agents/openai.yaml is not valid YAML")
        return
    if not isinstance(openai_data, dict) or not isinstance(openai_data.get("interface"), dict):
        err(name, "E9", "agents/openai.yaml must contain an interface mapping")
        return

    interface = openai_data["interface"]
    required_interface = ("display_name", "short_description", "default_prompt")
    for field in required_interface:
        if not isinstance(interface.get(field), str) or not interface[field].strip():
            err(name, "E9", f"interface.{field} must be a non-empty string")

    short_description = interface.get("short_description")
    if isinstance(short_description, str) and not 25 <= len(short_description) <= 64:
        err(
            name,
            "E10",
            f"interface.short_description must be 25-64 chars; got {len(short_description)}",
        )

    default_prompt = interface.get("default_prompt")
    if isinstance(default_prompt, str) and f"${name}" not in default_prompt:
        err(name, "E10", f"interface.default_prompt must mention '${name}'")

    source_rel = "references/authoritative-sources.md"
    source_registry = folder / source_rel
    if source_rel not in body:
        err(name, "E12", f"SKILL.md must link to {source_rel}")
    if not source_registry.exists():
        err(name, "E12", f"{source_rel} missing")
        return

    source_text = source_registry.read_text(encoding="utf-8")
    verified_match = re.search(r"^- Last verified: (\d{4}-\d{2}-\d{2})$", source_text, re.MULTILINE)
    if not verified_match:
        err(name, "E12", "source registry must declare '- Last verified: YYYY-MM-DD'")
    else:
        try:
            verified = date.fromisoformat(verified_match.group(1))
            age_days = (date.today() - verified).days
            # A source may be verified just after local midnight while a CI
            # runner is still on the previous UTC date. Allow that one-day
            # timezone boundary, but reject genuinely future-dated records.
            if age_days < -1:
                err(name, "E12", "source registry verification date is in the future")
            elif age_days > 400:
                warn(name, "W4", f"source registry is {age_days} days old")
        except ValueError:
            err(name, "E12", "source registry verification date is invalid")
    if not re.search(r"^- Review cadence: .+$", source_text, re.MULTILINE):
        err(name, "E12", "source registry must declare a review cadence")
    if not re.search(r"^- Refresh triggers: .+$", source_text, re.MULTILINE):
        err(name, "E12", "source registry must declare refresh triggers")
    if len(re.findall(r"https://", source_text)) < 2:
        err(name, "E12", "source registry must contain at least two HTTPS sources")


def main() -> int:
    folders = sorted(p for p in SKILLS.iterdir() if p.is_dir())
    if not folders:
        print("no skill folders found under skills/", file=sys.stderr)
        return 1
    for folder in folders:
        check_skill(folder)
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"\n{len(folders)} skills checked — {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
