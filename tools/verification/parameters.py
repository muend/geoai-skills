"""Write the parameters into the output, or the result is not reproducible.

Measured behaviour: "Delivers parameters in the output metadata" scored 0%.
The analysis picks a search radius, a viewshed observer height, a threshold, a
number of classes — and none of it reaches the artifact. The map is then
un-redoable even by the person who made it, because the choices lived only in
the conversation.

``ParameterLog`` records choices as they are made, including *why*, and emits
them into the artifact's metadata. ``check_parameters_emitted`` verifies that a
produced artifact actually carries the parameters an operation requires.

The required-parameter table is intentionally small and explicit. An operation
that is not in the table abstains rather than passing, because "I don't know
what this needs" is not "this is fine".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .result import Result, abstained, failed, passed

CHECK = "parameters.emitted"

REQUIRED_BY_OPERATION: dict[str, tuple[str, ...]] = {
    "choropleth": ("classification_method", "class_edges", "n_classes", "colour_scheme"),
    "kernel_density": ("bandwidth", "cell_size", "kernel"),
    "idw": ("power", "search_radius", "min_points"),
    "kriging": ("variogram_model", "nugget", "sill", "range", "n_lags"),
    "viewshed": ("observer_height", "target_height", "max_distance", "earth_curvature"),
    "watershed": ("flow_direction_algorithm", "accumulation_threshold", "fill_method"),
    "slope": ("algorithm", "z_factor", "cell_size"),
    "isochrone": ("mode", "cutoff_minutes", "speed_assumption", "network_date"),
    "buffer": ("distance", "distance_unit", "dissolve"),
    "hotspot": ("weights_type", "distance_band", "correction_method", "alpha"),
    "classification": ("classifier", "n_training_samples", "split_strategy", "random_seed"),
    "change_detection": ("method", "threshold", "class_edges", "date_pair"),
}


@dataclass
class ParameterLog:
    """Accumulate parameter choices with their justification."""

    operation: str
    entries: dict[str, dict[str, Any]] = field(default_factory=dict)

    def record(
        self,
        name: str,
        value: Any,
        *,
        because: str | None = None,
        unit: str | None = None,
    ) -> ParameterLog:
        entry: dict[str, Any] = {"value": value}
        if unit is not None:
            entry["unit"] = unit
        if because is not None:
            entry["rationale"] = because
        self.entries[name] = entry
        return self

    def as_metadata(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "parameters": {k: self.entries[k] for k in sorted(self.entries)},
        }

    def missing(self) -> list[str]:
        required = REQUIRED_BY_OPERATION.get(self.operation.strip().lower())
        if required is None:
            return []
        return [name for name in required if name not in self.entries]

    def unjustified(self) -> list[str]:
        return [
            name
            for name, entry in sorted(self.entries.items())
            if not entry.get("rationale")
        ]


def _flatten_keys(node: Any, found: set[str] | None = None) -> set[str]:
    found = set() if found is None else found
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(str(key))
            _flatten_keys(value, found)
    elif isinstance(node, list):
        for item in node:
            _flatten_keys(item, found)
    return found


def check_parameters_emitted(
    operation: str,
    metadata: dict[str, Any] | None,
    *,
    require_rationale: bool = False,
) -> Result:
    """Fail when an artifact's metadata omits a parameter the operation needs."""
    op = operation.strip().lower()
    required = REQUIRED_BY_OPERATION.get(op)
    if required is None:
        return abstained(
            CHECK,
            f"no required-parameter list registered for operation {operation!r}",
            known=sorted(REQUIRED_BY_OPERATION),
        )
    if not metadata:
        return failed(
            CHECK,
            f"{op} produced no metadata; none of its {len(required)} required "
            f"parameters were recorded",
            evidence=[f"required: {', '.join(required)}"],
            operation=op,
        )

    present = _flatten_keys(metadata)
    missing = [name for name in required if name not in present]

    if missing:
        return failed(
            CHECK,
            f"{len(missing)} required parameter(s) missing from {op} metadata; "
            f"the result cannot be reproduced",
            evidence=[f"missing: {name}" for name in missing]
            + [f"present: {', '.join(sorted(present & set(required))) or 'none'}"],
            operation=op,
            missing=missing,
        )

    if require_rationale:
        params = metadata.get("parameters")
        if isinstance(params, dict):
            unjustified = [
                name
                for name in required
                if isinstance(params.get(name), dict)
                and not params[name].get("rationale")
            ]
            if unjustified:
                return failed(
                    CHECK,
                    f"{len(unjustified)} parameter(s) recorded without a rationale",
                    evidence=[f"no rationale: {n}" for n in unjustified],
                    operation=op,
                )

    return passed(
        CHECK,
        f"all {len(required)} required parameters recorded for {op}",
        operation=op,
        n_required=len(required),
    )
