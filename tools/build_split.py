#!/usr/bin/env python3
"""Deterministic dev / held-out split for the evaluation suite.

The split is keyed by `case_id` and lives in `evals/split.json`, outside the
eval files. That is deliberate: assigning a case to held-out must not change the
suite hash, or every split revision would invalidate every published benchmark.

Two forced assignments carry all the honesty in this file:

* a case whose criteria were read during quality work goes to **dev**. It cannot
  test an improvement that was made while looking at it.
* a case written blind, by an author with no access to any result, goes to
  **held-out**. It is the only kind of case that can.

Everything else is stratified by (skill, primary case type) with a fixed seed,
so re-running produces a byte-identical file.

What this is not
----------------
It is not an information barrier. The suite is a public repository: every
held-out prompt and criterion is readable by anyone editing the skills. Holding
a case out is a commitment not to iterate against it, enforced by Gate C, which
refuses to let a benchmark report held-out numbers without an explicit,
reviewable disclosure. Calling it secrecy would be a lie; calling it restraint
is accurate and still worth something.

Usage:
    python tools/build_split.py            # check the committed split is current
    python tools/build_split.py --write    # regenerate it
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
INPUTS_PATH = ROOT / "evals" / "split-inputs.json"
SPLIT_PATH = ROOT / "evals" / "split.json"

SEED = 20260726
TARGET_HELDOUT_FRACTION = 0.40

# Ordered most-informative first: a case that is both a collision probe and a
# positive is stratified as a collision probe, because that is the property the
# split most needs to spread evenly.
TYPE_PRIORITY = (
    "collision",
    "ambiguous",
    "negative",
    "artifact-correctness",
    "positive",
)

SPLIT_NOTE = (
    "Discipline split, not an information barrier. The eval suite is a public "
    "repository: every case, prompt and criterion is readable by anyone editing "
    "the skills. Holding a case out therefore means a commitment not to iterate "
    "against it, enforced by Gate C in tools/check_regression_gates.py, which "
    "refuses a benchmark that reports held-out numbers without a reviewable "
    "disclosure. It does not mean the case is secret. The strongest cases in the "
    "held-out set are the ones written after the split by an author who never "
    "saw a result; the rest are held out by choice, which is weaker and is "
    "recorded here as such."
)


class SplitError(Exception):
    """Raised when the split cannot be built or does not match the committed file."""


def primary_type(case_types: list[str]) -> str:
    for candidate in TYPE_PRIORITY:
        if candidate in case_types:
            return candidate
    return sorted(case_types)[0] if case_types else "unknown"


def load_cases(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    """Read the minimum each case needs to be stratified — not its criteria."""
    cases: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob("evals/cases/*/evals.json")):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        for entry in data["evals"]:
            case_id = f"{data['skill']}/{entry['id']}"
            if case_id in cases:
                raise SplitError(f"duplicate case id across eval files: {case_id}")
            cases[case_id] = {
                "skill": data["skill"],
                "case_types": list(entry["case_types"]),
                "primary_type": primary_type(entry["case_types"]),
                "behavior_class": entry.get("behavior_class", "routing-only"),
                "critical": bool(entry.get("critical", False)),
            }
    return dict(sorted(cases.items()))


def load_inputs(path: Path = INPUTS_PATH) -> tuple[set[str], set[str]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    analysed = set(data["analysed_before_split"])
    blind = set(data["written_blind"])
    overlap = analysed & blind
    if overlap:
        raise SplitError(
            "a case cannot be both analysed and blind; the split would be "
            f"self-contradictory: {sorted(overlap)}"
        )
    return analysed, blind


def build(
    cases: dict[str, dict[str, Any]], analysed: set[str], blind: set[str]
) -> dict[str, Any]:
    unknown = sorted((analysed | blind) - set(cases))
    if unknown:
        raise SplitError(
            "split-inputs.json names cases that are not in the suite. Renaming a "
            "case silently drops it from the split, so this is an error rather "
            f"than a warning: {unknown}"
        )

    # noqa: S311 is deliberate. Unpredictability would be a defect here: the
    # split must be reproducible by anyone auditing a published result, so a
    # seeded Mersenne Twister is the right generator and a secure one is wrong.
    rng = random.Random(SEED)  # noqa: S311
    strata: dict[tuple[str, str], list[str]] = defaultdict(list)
    for case_id, meta in cases.items():
        strata[(meta["skill"], meta["primary_type"])].append(case_id)

    dev: set[str] = set()
    holdout: set[str] = set()

    for key in sorted(strata):
        members = sorted(strata[key])
        rng.shuffle(members)
        dev.update(c for c in members if c in analysed)
        holdout.update(c for c in members if c in blind)
        free = [c for c in members if c not in analysed and c not in blind]
        # The blind cases are already held out, so only top up to the target.
        want = round(len(members) * TARGET_HELDOUT_FRACTION)
        already = sum(1 for c in members if c in blind)
        take = max(0, min(want - already, len(free)))
        holdout.update(free[:take])
        dev.update(free[take:])

    # Every skill keeps at least one held-out case, or that skill has no
    # independent check at all and the split silently exempts it.
    holdout_skills = {cases[c]["skill"] for c in holdout}
    rescued: list[str] = []
    for skill in sorted({m["skill"] for m in cases.values()}):
        if skill in holdout_skills:
            continue
        spare = sorted(c for c in dev if cases[c]["skill"] == skill and c not in analysed)
        if not spare:
            raise SplitError(
                f"{skill}: every case was analysed before the split, so no "
                f"independent check is possible. Write a blind case for this "
                f"skill rather than moving an analysed one into held-out."
            )
        chosen = spare[0]
        dev.discard(chosen)
        holdout.add(chosen)
        rescued.append(chosen)

    if not dev.isdisjoint(holdout):
        raise SplitError(f"a case landed in both halves: {sorted(dev & holdout)}")
    if dev | holdout != set(cases):
        missing = sorted(set(cases) - (dev | holdout))
        raise SplitError(f"cases assigned to neither half: {missing}")
    if not analysed <= dev:
        raise SplitError(f"an analysed case reached held-out: {sorted(analysed - dev)}")
    if not blind <= holdout:
        raise SplitError(f"a blind case reached dev: {sorted(blind - holdout)}")

    payload: dict[str, Any] = {
        "schema_version": 1,
        "note": SPLIT_NOTE,
        "seed": SEED,
        "target_holdout_fraction": TARGET_HELDOUT_FRACTION,
        "case_count": len(cases),
        "forced_to_dev_because_analysed": sorted(analysed),
        "forced_to_holdout_because_blind": sorted(blind),
        "rescued_for_skill_coverage": rescued,
        "dev": sorted(dev),
        "holdout": sorted(holdout),
    }
    payload["assignment_sha256"] = assignment_sha256(payload)
    return payload


def assignment_sha256(payload: dict[str, Any]) -> str:
    """Hash the assignment only, so prose edits to the note do not churn it."""
    return hashlib.sha256(
        json.dumps(
            {"dev": sorted(payload["dev"]), "holdout": sorted(payload["holdout"])},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def serialise(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def report(cases: dict[str, dict[str, Any]], payload: dict[str, Any]) -> None:
    dev, hold = set(payload["dev"]), set(payload["holdout"])
    total = len(cases)
    print(
        f"{total} cases | dev {len(dev)} ({100 * len(dev) / total:.0f}%) "
        f"| held-out {len(hold)} ({100 * len(hold) / total:.0f}%)"
    )
    print(f"forced to dev (analysed):     {len(payload['forced_to_dev_because_analysed'])}")
    print(f"forced to held-out (blind):   {len(payload['forced_to_holdout_because_blind'])}")
    print(f"rescued for skill coverage:   {len(payload['rescued_for_skill_coverage'])}")
    print(f"assignment_sha256:            {payload['assignment_sha256'][:16]}")

    blind = set(payload["forced_to_holdout_because_blind"])
    print("\nper skill: dev / held-out (of which written blind)")
    per: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for case_id, meta in cases.items():
        row = per[meta["skill"]]
        if case_id in dev:
            row[0] += 1
        else:
            row[1] += 1
            row[2] += 1 if case_id in blind else 0
    for skill in sorted(per):
        d, h, b = per[skill]
        flag = "  <-- no blind case" if b == 0 else ""
        print(f"  {skill:34s} {d:2d} / {h:2d} ({b}){flag}")

    print("\nper case type: dev / held-out")
    pert: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for case_id, meta in cases.items():
        pert[meta["primary_type"]][0 if case_id in dev else 1] += 1
    for kind in sorted(pert):
        d, h = pert[kind]
        print(f"  {kind:22s} {d:3d} / {h:3d}   held-out {100 * h / (d + h):.0f}%")

    print("\nrouting / behaviour: dev / held-out")
    perb: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for case_id, meta in cases.items():
        key = "routing" if meta["behavior_class"] == "routing-only" else "behaviour"
        perb[key][0 if case_id in dev else 1] += 1
    for key in sorted(perb):
        d, h = perb[key]
        print(f"  {key:12s} {d:3d} / {h:3d}")

    crit_d = sum(1 for c, m in cases.items() if m["critical"] and c in dev)
    crit_h = sum(1 for c, m in cases.items() if m["critical"] and c in hold)
    print(f"\ncritical cases: dev {crit_d} / held-out {crit_h}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Regenerate evals/split.json instead of checking it.",
    )
    args = parser.parse_args(argv)

    try:
        cases = load_cases()
        analysed, blind = load_inputs()
        payload = build(cases, analysed, blind)
    except SplitError as error:
        print(f"split: FAIL\n  {error}", file=sys.stderr)
        return 1

    if args.write:
        SPLIT_PATH.write_text(serialise(payload), encoding="utf-8")
        report(cases, payload)
        print(f"\nwrote {SPLIT_PATH.relative_to(ROOT)}")
        return 0

    if not SPLIT_PATH.exists():
        print(
            f"error: {SPLIT_PATH.relative_to(ROOT)} is missing. Generate it with "
            f"--write.",
            file=sys.stderr,
        )
        return 1

    committed = json.loads(SPLIT_PATH.read_text(encoding="utf-8-sig"))
    if committed.get("assignment_sha256") != payload["assignment_sha256"]:
        covered = len(committed.get("dev", [])) + len(committed.get("holdout", []))
        print(
            "split: FAIL — the committed split does not match the split the "
            "current suite and inputs produce.\n"
            f"  committed  {committed.get('assignment_sha256', '(none)')}\n"
            f"  recomputed {payload['assignment_sha256']}\n"
            f"  committed covers {covered} cases; the suite now has {len(cases)}.\n"
            "  Cases were probably added without re-running --write. Re-run it and "
            "review the diff: a case moving from held-out to dev needs a reason.",
            file=sys.stderr,
        )
        return 1

    print(
        f"split: pass — {len(cases)} cases, "
        f"dev {len(payload['dev'])} / held-out {len(payload['holdout'])}, "
        f"assignment {payload['assignment_sha256'][:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
