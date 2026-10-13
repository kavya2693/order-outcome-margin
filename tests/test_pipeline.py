from pathlib import Path

import numpy as np

from order_margin.pipeline import Results, write


def _row(res: Results, model: str) -> dict:
    return res.metrics.set_index("model").loc[model].to_dict()


def test_true_probabilities_beat_every_model_on_log_loss(results: Results) -> None:
    truth = _row(results, "true probabilities (ceiling)")["log_loss"]
    others = results.metrics.query("model != 'true probabilities (ceiling)'")["log_loss"]
    assert (others > truth).all()


def test_models_beat_class_priors(results: Results) -> None:
    prior = _row(results, "class priors")["log_loss"]
    assert _row(results, "gbm + isotonic")["log_loss"] < prior
    assert _row(results, "logistic, raw")["log_loss"] < prior


def test_class_weighting_breaks_the_margin_forecast_and_isotonic_repairs_it(results: Results) -> None:
    raw = _row(results, "gbm class-weighted, raw")
    fixed = _row(results, "gbm class-weighted + isotonic")
    assert raw["ece_mean"] > 5 * _row(results, "gbm, raw")["ece_mean"]
    assert abs(raw["margin_bias_pct"]) > 0.5
    assert abs(fixed["margin_bias_pct"]) < 0.2


def test_margin_rule_beats_blocking_every_cod_order(results: Results) -> None:
    p = results.policy.set_index("policy")["margin_change"]
    assert p["margin rule, gbm + isotonic"] > p["block every COD order"]
    assert p["margin rule, true probabilities (ceiling)"] >= p["margin rule, gbm + isotonic"] - 1e-6
    assert p["no blocking"] == 0


def test_writes_every_output(results: Results, tmp_path: Path) -> None:
    write(results, tmp_path)
    for name in ["metrics.csv", "policy.csv", "report.md", "reliability.png", "policy_frontier.png"]:
        assert (tmp_path / name).stat().st_size > 0
    assert np.isfinite(results.metrics["log_loss"]).all()
