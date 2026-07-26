"""Command-line front end — the thing a skill contract actually invokes.

A skill's `## Verification (Required)` section should be able to say:

    python -m tools.verify choropleth --metadata outputs/map-metadata.json
    # non-zero exit means fix it before declaring success

That is the whole point of the toolkit: a prose instruction is compressible and
gets dropped, an exit code is not.

Exit codes:
    0  verified — no check found a violation
    1  FAILED — at least one check found a specific violation
    2  NOT VERIFIED — nothing failed, but at least one check could not run
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.verification import (
    Report,
    abstained,
    Scene,
    check_correction_applied,
    check_disaggregation,
    check_k_anonymity,
    check_parameters_emitted,
    check_planar_operation,
    check_shared_class_breaks,
    check_pipeline_order,
    check_vertical_horizontal_units,
    compare_scenes,
    verify_manifest,
)


def _load_json(path: str | None) -> dict | list | None:
    if not path:
        return None
    file = Path(path)
    if not file.exists():
        return None
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None



def _coerce(check: str, description: str, builder):
    """Turn a malformed payload into an ABSTAIN instead of a traceback.

    The toolkit's whole vocabulary rests on "could not verify" being distinct
    from "found a violation". A crash here collapsed the two: an unreadable
    input exited 1, which this tool defines as FAILED. Malformed input is an
    abstention, and it has to say so in the same channel as everything else.
    """
    try:
        return builder()
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        return abstained(check, f"{description}: {type(exc).__name__}: {exc}")


def cmd_units(args: argparse.Namespace, report: Report) -> None:
    report.add(check_planar_operation(args.operation, args.crs, value=args.value))
    if args.vertical_unit:
        report.add(check_vertical_horizontal_units(args.crs, args.vertical_unit))


def cmd_parameters(args: argparse.Namespace, report: Report) -> None:
    metadata = _load_json(args.metadata)
    if metadata is not None and not isinstance(metadata, dict):
        report.add(
            abstained(
                "parameters.emitted",
                f"{args.metadata} does not contain a JSON object",
            )
        )
        return
    report.add(
        check_parameters_emitted(
            args.operation, metadata, require_rationale=args.require_rationale
        )
    )


def cmd_provenance(args: argparse.Namespace, report: Report) -> None:
    manifest = _load_json(args.manifest)
    if not isinstance(manifest, dict):
        report.add(
            abstained(
                "provenance.manifest",
                f"could not read a manifest at {args.manifest}",
            )
        )
        return
    report.add(verify_manifest(manifest, strict=args.strict))


def cmd_multiplicity(args: argparse.Namespace, report: Report) -> None:
    payload = _load_json(args.p_values)
    if not isinstance(payload, list):
        report.add(
            abstained(
                "stats.multiplicity",
                f"could not read a p-value array from {args.p_values}",
            )
        )
        return
    report.add(
        _coerce(
            "stats.multiplicity",
            f"could not read p-values from {args.p_values}",
            lambda: check_correction_applied(
                args.reported,
                [float(v) for v in payload],
                alpha=args.alpha,
                dependent=not args.independent,
            ),
        )
    )


def cmd_comparability(args: argparse.Namespace, report: Report) -> None:
    payload = _load_json(args.scenes)
    if isinstance(payload, list):
        report.add(
            _coerce(
                "comparability.scenes",
                f"could not read scene descriptors from {args.scenes}",
                lambda: compare_scenes([Scene(**entry) for entry in payload]),
            )
        )
    breaks = _load_json(args.class_breaks)
    if isinstance(breaks, dict):
        report.add(
            _coerce(
                "comparability.class_breaks",
                f"could not read class breaks from {args.class_breaks}",
                lambda: check_shared_class_breaks(
                    {k: [float(x) for x in v] for k, v in breaks.items()}
                ),
            )
        )


def cmd_privacy(args: argparse.Namespace, report: Report) -> None:
    counts = _load_json(args.counts)
    if isinstance(counts, dict):
        report.add(
            _coerce(
                "privacy.k_anonymity",
                f"could not read counts from {args.counts}",
                lambda: check_k_anonymity(
                    {k: int(v) for k, v in counts.items()}, k=args.k
                ),
            )
        )


def cmd_equity(args: argparse.Namespace, report: Report) -> None:
    payload = _load_json(args.groups)
    if isinstance(payload, dict):
        report.add(
            _coerce(
                "equity.disaggregated",
                f"could not read grouped values from {args.groups}",
                lambda: check_disaggregation(
                    {k: [float(x) for x in v] for k, v in payload.items()},
                    threshold=args.threshold,
                ),
            )
        )


def cmd_ordering(args: argparse.Namespace, report: Report) -> None:
    report.add(check_pipeline_order(args.steps))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verify", description="Executable checks for geospatial discipline."
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    units = sub.add_parser("units", help="metric operation on the wrong CRS")
    units.add_argument("operation")
    units.add_argument("--crs", required=True)
    units.add_argument("--value", type=float)
    units.add_argument("--vertical-unit")
    units.set_defaults(func=cmd_units)

    params = sub.add_parser("parameters", help="required parameters reached the metadata")
    params.add_argument("operation")
    params.add_argument("--metadata", required=True)
    params.add_argument("--require-rationale", action="store_true")
    params.set_defaults(func=cmd_parameters)

    prov = sub.add_parser("provenance", help="manifest supports reproduction")
    prov.add_argument("--manifest", required=True)
    prov.add_argument("--strict", action="store_true")
    prov.set_defaults(func=cmd_provenance)

    mult = sub.add_parser("multiplicity", help="correction applied before mapping")
    mult.add_argument("--p-values", required=True, help="JSON array of p-values")
    mult.add_argument("--reported", type=int, required=True)
    mult.add_argument("--alpha", type=float, default=0.05)
    mult.add_argument("--independent", action="store_true")
    mult.set_defaults(func=cmd_multiplicity)

    comp = sub.add_parser("comparability", help="scenes and class breaks are comparable")
    comp.add_argument("--scenes", help="JSON array of scene descriptors")
    comp.add_argument("--class-breaks", help="JSON object of date -> edges")
    comp.set_defaults(func=cmd_comparability)

    priv = sub.add_parser("privacy", help="released cells meet k-anonymity")
    priv.add_argument("--counts", required=True, help="JSON object of cell -> count")
    priv.add_argument("-k", type=int, default=5)
    priv.set_defaults(func=cmd_privacy)

    eq = sub.add_parser("equity", help="groups reported, disparity surfaced")
    eq.add_argument("--groups", required=True, help="JSON object of group -> values")
    eq.add_argument("--threshold", type=float)
    eq.set_defaults(func=cmd_equity)

    order = sub.add_parser("ordering", help="pipeline steps in a valid order")
    order.add_argument("steps", nargs="+")
    order.set_defaults(func=cmd_ordering)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = Report()
    args.func(args, report)
    print(report.to_json() if args.json else report.render())
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
