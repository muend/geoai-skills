"""AHP weights + consistency ratio from a pairwise comparison matrix.

Run:    python ahp_weights.py matrix.csv        (n x n CSV, no header)
Import: from ahp_weights import ahp_weights
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

# Saaty's random consistency index by matrix order
RI = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}


def ahp_weights(A: np.ndarray) -> tuple[np.ndarray, float]:
    """Principal-eigenvector AHP weights and consistency ratio.

    Args:
        A: n x n positive reciprocal pairwise comparison matrix
           (Saaty 1-9 scale).

    Returns:
        (weights summing to 1, CR). CR >= 0.10 means judgments are too
        inconsistent to use — revise the most discordant comparison.

    Raises:
        ValueError: If the matrix is not finite, positive, square, reciprocal,
            or supported by the bundled random consistency index table.
    """
    A = np.asarray(A, dtype=float)
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise ValueError("AHP matrix must be a square 2D array.")

    n = A.shape[0]
    if n not in RI:
        raise ValueError(f"AHP matrix order {n} is unsupported; expected 1–10.")
    if not np.isfinite(A).all():
        raise ValueError("AHP matrix must contain only finite values.")
    if np.any(A <= 0):
        raise ValueError("AHP matrix values must be strictly positive.")
    if not np.allclose(np.diag(A), 1.0, rtol=0.0, atol=1e-8):
        raise ValueError("AHP matrix diagonal must contain only 1 values.")
    if not np.allclose(A * A.T, np.ones_like(A), rtol=1e-6):
        raise ValueError("Matrix is not reciprocal (A[i,j] must equal 1/A[j,i]).")

    eigvals, eigvecs = np.linalg.eig(A)
    k = int(np.argmax(eigvals.real))
    if abs(eigvals[k].imag) > 1e-8:
        raise ValueError("Principal eigenvalue is unexpectedly complex.")

    w = eigvecs[:, k].real
    if w.sum() < 0:
        w = -w
    if np.any(w <= 0):
        raise ValueError("Principal eigenvector did not produce positive weights.")
    w /= w.sum()
    lam_max = eigvals[k].real
    ci = max(0.0, (lam_max - n) / (n - 1)) if n > 2 else 0.0
    cr = ci / RI[n] if RI.get(n, 0) > 0 else 0.0
    return w, float(cr)


def main() -> None:
    """Read a headerless CSV matrix and print weights plus consistency."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", type=Path)
    args = parser.parse_args()

    matrix = np.loadtxt(args.matrix, delimiter=",")
    weights, cr = ahp_weights(matrix)
    for i, wi in enumerate(weights):
        print(f"criterion_{i + 1}: {wi:.4f}")
    verdict = "OK" if cr < 0.10 else "REVISE — inconsistent judgments"
    print(f"CR = {cr:.4f}  [{verdict}]")


if __name__ == "__main__":
    main()
