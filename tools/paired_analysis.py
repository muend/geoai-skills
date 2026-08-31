"""Paired enabled/disabled analysis for the GeoAI behavior run.

`tools/eval_runner.py score` scores ONE condition. Nothing in the repository
joins the two arms, so the matched comparison the pre-registration commits to -
case-level and criterion-level win/loss/tie plus a sign test at both levels -
has no implementation. This is that implementation.

Two modes, both driven by the same suite hash:

* execution   - always available. Reads each arm's adapter response checkpoint
                and reports activation, cost, latency, tokens and errors.
                No judgments required.
* judgment    - requires a judgments.json per arm (model screen or human).
                Adds case-level pass, criterion-level coverage, matched
                win/loss/tie and exact two-sided sign tests.

Nothing here writes to the frozen suite. Read-only over run directories.

Usage (from the repository root):

    python tools/paired_analysis.py \
        --suite 520bc41dd4c0 \
        [--enabled-judgments PATH --disabled-judgments PATH] \
        [--json OUT.json]
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

RUNS = Path("evals/runs")


# --------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------

def sign_test(wins: int, losses: int) -> dict[str, Any]:
    """Exact two-sided binomial sign test. Ties are excluded, per convention.

    Implemented locally rather than pulling scipy: the repository's dev
    dependencies do not include it, and an exact test over n < 1000 is three
    lines of math.comb.
    """
    n = wins + losses
    if n == 0:
        return {"n": 0, "wins": wins, "losses": losses, "p_value": None,
                "interpretation": "no discordant pairs; test undefined"}
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    p = min(1.0, 2 * tail)
    if p < 0.001:
        verdict = "significant at p<0.001"
    elif p < 0.01:
        verdict = "significant at p<0.01"
    elif p < 0.05:
        verdict = "significant at p<0.05"
    else:
        verdict = "not significant at p<0.05"
    # The stored value is unrounded: a strong effect over ~90 pairs produces p
    # on the order of 1e-12, and any fixed-decimal rounding collapses it to 0.0.
    # Formatting happens at render time, so the JSON stays re-analysable.
    return {"n": n, "wins": wins, "losses": losses,
            "p_value": p, "interpretation": verdict}


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def run_dir(suite: str, condition: str, runs: Path,
            runtime: str | None = None) -> Path:
    """Resolve the primary run directory for a condition.

    The suffix must NOT be wildcarded. Retry and diagnostic runs live in
    directories that extend the primary name (`…--review-mode-retry-1`,
    `…--maxturns12-diagnostic-1`), and a trailing wildcard silently matched
    them; sorted()[-1] then selected a one-case retry directory and the
    execution block reported zero matched pairs from a completed 93-case run.
    Exact match only, and refuse ambiguity rather than guessing.
    """
    pattern = (f"{runtime}--*--skills-{condition}--behavior--{suite}" if runtime
               else f"*--skills-{condition}--behavior--{suite}")
    matches = sorted(runs.glob(pattern))
    if not matches:
        near = sorted(runs.glob(f"*--skills-{condition}--behavior--{suite}*"))
        hint = ("\nDirectories that extend this name exist and were NOT used: "
                + ", ".join(m.name for m in near)) if near else ""
        raise SystemExit(
            f"no primary run directory for condition {condition!r}, suite {suite!r}{hint}")
    if len(matches) > 1:
        raise SystemExit(
            f"ambiguous primary run directory for {condition!r} / {suite!r}: "
            + ", ".join(m.name for m in matches)
            + "\nPass --runtime to disambiguate, e.g. --runtime claude-code-2-1-222")
    return matches[0]


def load_responses(directory: Path) -> dict[str, dict]:
    path = directory / "adapter" / "claude-code.responses.jsonl"
    if not path.exists():
        raise SystemExit(f"missing response checkpoint: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]
    return {row["case_id"]: row for row in rows}


def load_judgments(path: Path | None, suite_sha: str) -> dict[str, dict] | None:
    if path is None:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    declared = payload.get("suite_sha256", "")
    if declared != suite_sha and not declared.startswith(suite_sha):
        print(f"WARNING: judgment suite_sha256 {declared!r} "
              f"does not match run suite {suite_sha!r}", file=sys.stderr)
    return {row["case_id"]: row for row in payload["judgments"]}


# --------------------------------------------------------------------------
# execution-level
# --------------------------------------------------------------------------

def execution_block(cases: list[dict], en: dict, dis: dict) -> dict[str, Any]:
    paired, en_only, dis_only, errored = [], [], [], []
    for case in cases:
        cid = case["case_id"]
        e, d = en.get(cid), dis.get(cid)
        if e is None and d is None:
            continue
        if e is None:
            dis_only.append(cid)
            continue
        if d is None:
            en_only.append(cid)
            continue
        if e.get("error") or d.get("error"):
            errored.append({"case_id": cid,
                            "enabled_error": e.get("error"),
                            "disabled_error": d.get("error")})
            continue
        paired.append((case, e, d))

    def agg(rows: list[dict], key) -> dict[str, float]:
        vals = [key(r) for r in rows]
        return {"mean": round(statistics.mean(vals), 4) if vals else 0.0,
                "median": round(statistics.median(vals), 4) if vals else 0.0,
                "total": round(sum(vals), 4)}

    e_rows = [e for _, e, _ in paired]
    d_rows = [d for _, _, d in paired]
    longer = sum(1 for _, e, d in paired
                 if len(e.get("response") or "") > len(d.get("response") or ""))
    activated_enabled = sum(1 for r in e_rows if r.get("activated_skills"))
    activated_disabled = sum(1 for r in d_rows if r.get("activated_skills"))

    route_ok = 0
    route_missing = []
    for case, e, _ in paired:
        expected = set(case.get("expected_route") or [])
        actual = set(e.get("activated_skills") or [])
        if not expected or expected <= actual:
            route_ok += 1
        else:
            route_missing.append({"case_id": case["case_id"],
                                  "expected": sorted(expected),
                                  "actual": sorted(actual)})

    return {
        "cases_in_suite": len(cases),
        "responded_enabled": len(en),
        "responded_disabled": len(dis),
        "clean_matched_pairs": len(paired),
        "errored_pairs": errored,
        "unpaired_enabled_only": en_only,
        "unpaired_disabled_only": dis_only,
        "activation": {
            "enabled": f"{activated_enabled}/{len(paired)}",
            "disabled_control": f"{activated_disabled}/{len(paired)}",
            "control_clean": activated_disabled == 0,
        },
        "expected_route_satisfied": f"{route_ok}/{len(paired)}",
        "route_shortfalls": route_missing,
        "cost_usd": {"enabled": agg(e_rows, lambda r: r.get("cost_usd") or 0.0),
                     "disabled": agg(d_rows, lambda r: r.get("cost_usd") or 0.0)},
        "latency_s": {"enabled": agg(e_rows, lambda r: (r.get("latency_ms") or 0) / 1000),
                      "disabled": agg(d_rows, lambda r: (r.get("latency_ms") or 0) / 1000)},
        "output_tokens": {
            "enabled": agg(e_rows, lambda r: r.get("usage", {}).get("output_tokens", 0)),
            "disabled": agg(d_rows, lambda r: r.get("usage", {}).get("output_tokens", 0)),
        },
        "response_chars": {"enabled": agg(e_rows, lambda r: len(r.get("response") or "")),
                           "disabled": agg(d_rows, lambda r: len(r.get("response") or ""))},
        "enabled_response_longer": f"{longer}/{len(paired)}",
    }


# --------------------------------------------------------------------------
# judgment-level
# --------------------------------------------------------------------------

def _criterion_map(judgment: dict) -> dict[str, bool]:
    return {item["criterion"]: bool(item["met"]) for item in judgment["expected_behavior"]}


def judgment_block(cases: list[dict], en_j: dict, dis_j: dict,
                   en_r: dict, dis_r: dict) -> dict[str, Any]:
    case_w = case_l = case_t = 0
    crit_w = crit_l = crit_t = 0
    per_skill: dict[str, Counter] = defaultdict(Counter)
    per_case: list[dict] = []
    en_met = en_tot = dis_met = dis_tot = 0
    en_pass = dis_pass = judged = 0
    en_crit_fail = dis_crit_fail = 0
    en_forbidden = dis_forbidden = 0
    crit_subset = {"wins": 0, "losses": 0, "ties": 0}
    low_resolution = []

    for case in cases:
        cid = case["case_id"]
        ej, dj = en_j.get(cid), dis_j.get(cid)
        if ej is None or dj is None:
            continue
        if (en_r.get(cid, {}).get("error") or dis_r.get(cid, {}).get("error")):
            continue
        judged += 1
        em, dm = _criterion_map(ej), _criterion_map(dj)
        shared = [c for c in em if c in dm]
        e_hits = sum(em[c] for c in shared)
        d_hits = sum(dm[c] for c in shared)
        total = len(shared)
        en_met += e_hits
        dis_met += d_hits
        en_tot += total
        dis_tot += total

        if total <= 2:
            low_resolution.append(cid)

        for c in shared:
            if em[c] and not dm[c]:
                crit_w += 1
                per_skill[case["skill"]]["crit_win"] += 1
            elif dm[c] and not em[c]:
                crit_l += 1
                per_skill[case["skill"]]["crit_loss"] += 1
            else:
                crit_t += 1
                per_skill[case["skill"]]["crit_tie"] += 1

        e_all = total > 0 and e_hits == total
        d_all = total > 0 and d_hits == total
        en_pass += int(e_all)
        dis_pass += int(d_all)
        if e_hits > d_hits:
            outcome = "enabled"
            case_w += 1
            per_skill[case["skill"]]["case_win"] += 1
        elif d_hits > e_hits:
            outcome = "disabled"
            case_l += 1
            per_skill[case["skill"]]["case_loss"] += 1
        else:
            outcome = "tie"
            case_t += 1
            per_skill[case["skill"]]["case_tie"] += 1

        if case.get("critical"):
            key = {"enabled": "wins", "disabled": "losses", "tie": "ties"}[outcome]
            crit_subset[key] += 1

        en_crit_fail += int(bool(ej.get("critical_failure")))
        dis_crit_fail += int(bool(dj.get("critical_failure")))
        en_forbidden += sum(1 for f in ej.get("forbidden_behavior", []) if f.get("violated"))
        dis_forbidden += sum(1 for f in dj.get("forbidden_behavior", []) if f.get("violated"))

        per_case.append({"case_id": cid, "skill": case["skill"],
                         "critical": bool(case.get("critical")),
                         "criteria": total,
                         "enabled_met": e_hits, "disabled_met": d_hits,
                         "outcome": outcome})

    return {
        "judged_pairs": judged,
        "case_level": {
            "enabled_all_criteria_met": f"{en_pass}/{judged}",
            "disabled_all_criteria_met": f"{dis_pass}/{judged}",
            "wins_enabled": case_w, "wins_disabled": case_l, "ties": case_t,
            "sign_test": sign_test(case_w, case_l),
        },
        "criterion_level": {
            "enabled_coverage": f"{en_met}/{en_tot}"
                                + (f" ({en_met / en_tot:.1%})" if en_tot else ""),
            "disabled_coverage": f"{dis_met}/{dis_tot}"
                                 + (f" ({dis_met / dis_tot:.1%})" if dis_tot else ""),
            "wins_enabled": crit_w, "wins_disabled": crit_l, "ties": crit_t,
            "sign_test": sign_test(crit_w, crit_l),
        },
        "critical_subset_case_level": {
            **crit_subset,
            "sign_test": sign_test(crit_subset["wins"], crit_subset["losses"]),
        },
        "critical_spatial_failure": {
            "enabled": en_crit_fail, "disabled": dis_crit_fail, "judged": judged,
        },
        "forbidden_violations": {"enabled": en_forbidden, "disabled": dis_forbidden},
        "low_resolution_cases": {
            "count": len(low_resolution),
            "note": "<=2 criteria; structurally unable to separate the arms",
            "case_ids": low_resolution,
        },
        "per_skill": {k: dict(v) for k, v in sorted(per_skill.items())},
        "per_case": per_case,
    }


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def _fmt_p(p: float | None) -> str:
    return "n/a" if p is None else (f"{p:.3g}" if p < 0.001 else f"{p:.4f}")


def render(report: dict[str, Any]) -> str:
    out: list[str] = []
    a = out.append
    ex = report["execution"]
    a(f"suite {report['suite']}  |  runtime {report['runtime']}  |  model {report['model']}")
    a("")
    a("EXECUTION")
    a(f"  suite cases              {ex['cases_in_suite']}")
    a(f"  responded                enabled {ex['responded_enabled']}"
      f" / disabled {ex['responded_disabled']}")
    a(f"  clean matched pairs      {ex['clean_matched_pairs']}")
    a(f"  activation (enabled)     {ex['activation']['enabled']}")
    a(f"  activation (control)     {ex['activation']['disabled_control']}"
      f"  -> {'CLEAN' if ex['activation']['control_clean'] else 'CONTAMINATED'}")
    a(f"  expected route satisfied {ex['expected_route_satisfied']}")
    a(f"  enabled response longer  {ex['enabled_response_longer']}")
    a(f"  cost total               enabled ${ex['cost_usd']['enabled']['total']:.4f}"
      f" / disabled ${ex['cost_usd']['disabled']['total']:.4f}")
    a(f"  output tokens (mean)     enabled {ex['output_tokens']['enabled']['mean']:.0f}"
      f" / disabled {ex['output_tokens']['disabled']['mean']:.0f}")
    if ex["errored_pairs"]:
        a(f"  errored pairs            {len(ex['errored_pairs'])}")
        for e in ex["errored_pairs"]:
            a(f"    {e['case_id']}")
            if e["enabled_error"]:
                a(f"      enabled : {e['enabled_error']}")
            if e["disabled_error"]:
                a(f"      disabled: {e['disabled_error']}")
    if ex["route_shortfalls"]:
        a(f"  route shortfalls         {len(ex['route_shortfalls'])}")
        for r in ex["route_shortfalls"]:
            a(f"    {r['case_id']}: expected {r['expected']} got {r['actual']}")

    j = report.get("judgment")
    if not j:
        a("")
        a("JUDGMENT")
        a("  no judgments supplied - pass --enabled-judgments / --disabled-judgments")
        a("  (execution numbers above are complete and require no judge)")
        return "\n".join(out)

    a("")
    a("JUDGMENT")
    a(f"  judged pairs             {j['judged_pairs']}")
    c = j["case_level"]
    a("  case level")
    a(f"    all criteria met       enabled {c['enabled_all_criteria_met']}"
      f" / disabled {c['disabled_all_criteria_met']}")
    a(f"    win / loss / tie       {c['wins_enabled']} / {c['wins_disabled']} / {c['ties']}")
    a(f"    sign test              n={c['sign_test']['n']}"
      f" p={_fmt_p(c['sign_test']['p_value'])} - {c['sign_test']['interpretation']}")
    k = j["criterion_level"]
    a("  criterion level")
    a(f"    coverage               enabled {k['enabled_coverage']}")
    a(f"                           disabled {k['disabled_coverage']}")
    a(f"    win / loss / tie       {k['wins_enabled']} / {k['wins_disabled']} / {k['ties']}")
    a(f"    sign test              n={k['sign_test']['n']}"
      f" p={_fmt_p(k['sign_test']['p_value'])} - {k['sign_test']['interpretation']}")
    cs = j["critical_subset_case_level"]
    a("  critical subset (case level)")
    a(f"    win / loss / tie       {cs['wins']} / {cs['losses']} / {cs['ties']}")
    a(f"    sign test              n={cs['sign_test']['n']}"
      f" p={_fmt_p(cs['sign_test']['p_value'])} - {cs['sign_test']['interpretation']}")
    cf = j["critical_spatial_failure"]
    a(f"  critical spatial failure enabled {cf['enabled']}/{cf['judged']}"
      f" / disabled {cf['disabled']}/{cf['judged']}")
    fv = j["forbidden_violations"]
    a(f"  forbidden violations     enabled {fv['enabled']} / disabled {fv['disabled']}")
    lr = j["low_resolution_cases"]
    a(f"  low-resolution cases     {lr['count']} ({lr['note']})")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--suite", required=True, help="suite hash prefix, e.g. 520bc41dd4c0")
    p.add_argument("--runs-dir", type=Path, default=RUNS)
    p.add_argument("--runtime", default=None,
                   help="directory-name runtime prefix, e.g. claude-code-2-1-222; "
                        "required when more than one runtime prepared this suite")
    p.add_argument("--enabled-judgments", type=Path, default=None)
    p.add_argument("--disabled-judgments", type=Path, default=None)
    p.add_argument("--json", type=Path, default=None, help="write the full report as JSON")
    args = p.parse_args(argv)

    en_dir = run_dir(args.suite, "enabled", args.runs_dir, args.runtime)
    dis_dir = run_dir(args.suite, "disabled", args.runs_dir, args.runtime)
    manifest = json.loads((en_dir / "manifest.json").read_text(encoding="utf-8"))
    cases = manifest["cases"]

    en_r, dis_r = load_responses(en_dir), load_responses(dis_dir)
    report: dict[str, Any] = {
        "suite": manifest["suite_sha256"],
        "runtime": manifest["runtime"],
        "model": manifest["model"],
        "enabled_run_dir": en_dir.name,
        "disabled_run_dir": dis_dir.name,
        "execution": execution_block(cases, en_r, dis_r),
    }
    en_j = load_judgments(args.enabled_judgments, manifest["suite_sha256"])
    dis_j = load_judgments(args.disabled_judgments, manifest["suite_sha256"])
    if en_j is not None and dis_j is not None:
        report["judgment"] = judgment_block(cases, en_j, dis_j, en_r, dis_r)

    print(render(report))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nJSON written: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
