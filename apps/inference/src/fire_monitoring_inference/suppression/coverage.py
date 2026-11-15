from __future__ import annotations

import numpy as np


def max_std(covariance) -> float:
    values = np.linalg.eigvalsh(np.asarray(covariance, dtype=float))
    return float(np.sqrt(max(float(values[-1]), 0.0)))


def cover_probability(covariance, radius: float, *, samples: int = 8000, seed: int = 0) -> float:
    if radius < 0:
        raise ValueError("coverage radius must be non-negative")
    cov = np.asarray(covariance, dtype=float)
    if cov.shape == (3, 3) and np.allclose(cov, cov[0, 0] * np.eye(3)):
        variance = float(cov[0, 0])
        if variance <= 0:
            return 1.0
        from scipy.stats import chi2

        return float(chi2.cdf((radius * radius) / variance, df=3))
    draws = np.random.default_rng(seed).multivariate_normal(np.zeros(3), cov, size=samples)
    return float(np.mean(np.sum(draws * draws, axis=1) <= radius * radius))


def prefix_cover_probabilities(
    covariance, offsets, radius: float, *, samples: int = 2000, seed: int = 0
) -> list[float]:
    if radius < 0:
        raise ValueError("coverage radius must be non-negative")
    points = np.asarray(offsets, dtype=float).reshape(-1, 3)
    if len(points) == 0:
        return []
    cov = np.asarray(covariance, dtype=float)
    draws = np.random.default_rng(seed).multivariate_normal(np.zeros(3), cov, size=samples)
    covered = np.zeros(len(draws), dtype=bool)
    probabilities = []
    for point in points:
        covered |= np.linalg.norm(draws - point, axis=1) <= radius
        probabilities.append(float(np.mean(covered)))
    return probabilities


def pattern_cover_probability(covariance, offsets, radius: float, *, samples: int = 2000, seed: int = 0) -> float:
    probabilities = prefix_cover_probabilities(
        covariance, offsets, radius, samples=samples, seed=seed
    )
    if not probabilities:
        return 0.0
    return probabilities[-1]
