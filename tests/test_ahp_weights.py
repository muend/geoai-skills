from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "mcda-suitability-analysis"
    / "scripts"
    / "ahp_weights.py"
)
SPEC = importlib.util.spec_from_file_location("ahp_weights_script", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ahp_weights = MODULE.ahp_weights


def test_consistent_matrix_recovers_expected_weights() -> None:
    expected = np.array([0.5, 0.3, 0.2])
    matrix = expected[:, None] / expected[None, :]

    weights, cr = ahp_weights(matrix)

    np.testing.assert_allclose(weights, expected, atol=1e-8)
    assert cr == pytest.approx(0.0, abs=1e-10)


@pytest.mark.parametrize(
    "matrix, message",
    [
        (np.ones((2, 3)), "square"),
        (np.array([[1.0, 0.0], [1.0, 1.0]]), "strictly positive"),
        (np.array([[1.0, np.nan], [1.0, 1.0]]), "finite"),
        (np.array([[2.0, 1.0], [1.0, 1.0]]), "diagonal"),
        (np.array([[1.0, 2.0], [0.4, 1.0]]), "reciprocal"),
        (np.ones((11, 11)), "unsupported"),
    ],
)
def test_invalid_matrices_fail_loudly(matrix: np.ndarray, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ahp_weights(matrix)


def test_inconsistent_matrix_reports_high_consistency_ratio() -> None:
    matrix = np.array(
        [
            [1.0, 9.0, 1.0 / 3.0],
            [1.0 / 9.0, 1.0, 7.0],
            [3.0, 1.0 / 7.0, 1.0],
        ]
    )

    _, cr = ahp_weights(matrix)

    assert cr >= 0.10

