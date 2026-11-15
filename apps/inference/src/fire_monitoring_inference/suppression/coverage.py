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


def pattern_cover_probability(covariance, offsets, radius: float, *, samples: int = 2000, seed: int = 0) -> float:
    if radius < 0:
        raise ValueError("coverage radius must be non-negative")
    points = np.asarray(offsets, dtype=float)
    if points.size == 0:
        return 0.0
    points = points.reshape(-1, 3)
    cov = np.asarray(covariance, dtype=float)
    draws = np.random.default_rng(seed).multivariate_normal(np.zeros(3), cov, size=samples)
    distance = np.linalg.norm(draws[:, None, :] - points[None, :, :], axis=2)
    return float(np.mean(np.any(distance <= radius, axis=1)))
