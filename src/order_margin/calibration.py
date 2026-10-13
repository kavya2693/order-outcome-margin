"""Multiclass calibration and the metrics that judge it.

Calibrators are fitted one class against the rest on a window the booster never saw,
then each row is renormalised to sum to one. Renormalising slightly undoes the
per-class fit, which is why calibration error is measured after it, not before.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from order_margin.config import N_CLASSES

EPS = 1e-6


def _renorm(P: np.ndarray) -> np.ndarray:
    P = np.clip(P, EPS, None)
    return np.asarray(P / P.sum(axis=1, keepdims=True))


@dataclass
class IsotonicCalibrator:
    fits: list[IsotonicRegression] = field(default_factory=list)

    def fit(self, P: np.ndarray, y: np.ndarray) -> IsotonicCalibrator:
        self.fits = []
        for k in range(P.shape[1]):
            iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
            iso.fit(P[:, k], (y == k).astype(float))
            self.fits.append(iso)
        return self

    def transform(self, P: np.ndarray) -> np.ndarray:
        return _renorm(np.column_stack([f.predict(P[:, k]) for k, f in enumerate(self.fits)]))


@dataclass
class PlattCalibrator:
    fits: list[LogisticRegression] = field(default_factory=list)

    @staticmethod
    def _logit(p: np.ndarray) -> np.ndarray:
        p = np.clip(p, EPS, 1 - EPS)
        return np.log(p / (1 - p)).reshape(-1, 1)

    def fit(self, P: np.ndarray, y: np.ndarray) -> PlattCalibrator:
        self.fits = []
        for k in range(P.shape[1]):
            lr = LogisticRegression(C=1e4, max_iter=500)
            lr.fit(self._logit(P[:, k]), (y == k).astype(int))
            self.fits.append(lr)
        return self

    def transform(self, P: np.ndarray) -> np.ndarray:
        cols = [f.predict_proba(self._logit(P[:, k]))[:, 1] for k, f in enumerate(self.fits)]
        return _renorm(np.column_stack(cols))


def classwise_ece(P: np.ndarray, y: np.ndarray, n_bins: int = 15) -> np.ndarray:
    """Expected calibration error per class, equal-mass bins.

    Equal-mass rather than equal-width because the rare classes put almost every
    prediction in the first width bin, which would hide all their miscalibration.
    """
    out = np.zeros(P.shape[1])
    for k in range(P.shape[1]):
        p = P[:, k]
        hit = (y == k).astype(float)
        order = np.argsort(p, kind="stable")
        for b in np.array_split(order, n_bins):
            if len(b):
                out[k] += len(b) / len(p) * abs(p[b].mean() - hit[b].mean())
    return out


def log_loss(P: np.ndarray, y: np.ndarray) -> float:
    return float(-np.mean(np.log(np.clip(P[np.arange(len(y)), y], EPS, 1.0))))


def macro_f1(P: np.ndarray, y: np.ndarray) -> float:
    pred = P.argmax(axis=1)
    f1s = []
    for k in range(N_CLASSES):
        tp = float(np.sum((pred == k) & (y == k)))
        fp = float(np.sum((pred == k) & (y != k)))
        fn = float(np.sum((pred != k) & (y == k)))
        f1s.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return float(np.mean(f1s))


def count_ratio(P: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Predicted over observed count per class; 1.0 means totals are right."""
    observed = np.bincount(y, minlength=P.shape[1]).astype(float)
    return np.asarray(P.sum(axis=0) / np.maximum(observed, 1.0))


def reliability_curve(p: np.ndarray, hit: np.ndarray, n_bins: int = 15) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(p, kind="stable")
    bins = [b for b in np.array_split(order, n_bins) if len(b)]
    return np.array([p[b].mean() for b in bins]), np.array([hit[b].mean() for b in bins])
