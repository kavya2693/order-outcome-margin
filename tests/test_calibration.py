import numpy as np

from order_margin.calibration import (
    IsotonicCalibrator,
    PlattCalibrator,
    classwise_ece,
    count_ratio,
    log_loss,
    macro_f1,
)


def _calibrated_sample(n: int = 60_000, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1.2, (n, 5)) + np.array([3.0, 1.0, 0.5, 0.3, -2.0])
    P = np.exp(z) / np.exp(z).sum(axis=1, keepdims=True)
    y = (rng.random(n)[:, None] > np.cumsum(P, axis=1)).sum(axis=1).clip(0, 4)
    return P, y


def _overconfident(P: np.ndarray) -> np.ndarray:
    Q = P**2.5
    return Q / Q.sum(axis=1, keepdims=True)


def test_ece_is_near_zero_for_calibrated_and_large_for_broken_predictions() -> None:
    P, y = _calibrated_sample()
    assert classwise_ece(P, y).mean() < 0.005
    assert classwise_ece(_overconfident(P), y).mean() > 4 * classwise_ece(P, y).mean()
    assert np.allclose(count_ratio(P, y), 1.0, atol=0.06)


def test_calibrators_repair_an_overconfident_model_on_fresh_data() -> None:
    P, y = _calibrated_sample(seed=1)
    P2, y2 = _calibrated_sample(seed=2)
    bad = _overconfident(P)
    for cal in (IsotonicCalibrator().fit(bad, y), PlattCalibrator().fit(bad, y)):
        fixed = cal.transform(_overconfident(P2))
        assert np.allclose(fixed.sum(axis=1), 1.0)
        assert classwise_ece(fixed, y2).mean() < 0.5 * classwise_ece(_overconfident(P2), y2).mean()
        assert log_loss(fixed, y2) < log_loss(_overconfident(P2), y2)


def test_macro_f1_and_log_loss_on_known_cases() -> None:
    y = np.array([0, 1, 2, 3, 4])
    assert macro_f1(np.eye(5)[y], y) == 1.0
    # Always predicting the majority class scores 1/5 of a perfect F1 on one class only.
    assert macro_f1(np.tile([1.0, 0, 0, 0, 0], (5, 1)), y) < 0.1
    assert np.isclose(log_loss(np.full((5, 5), 0.2), y), np.log(5))
