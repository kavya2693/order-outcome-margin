"""Markdown report written next to the CSVs, so every README number has a source file."""

from __future__ import annotations

import pandas as pd

from order_margin.pipeline import Results


def _table(df: pd.DataFrame, fmt: dict[str, str]) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            cells.append(format(v, fmt[c]) if c in fmt and pd.notna(v) else str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render(res: Results) -> str:
    s = res.summary
    model_cols = ["model", "macro_f1", "log_loss", "ece_mean", "ece_fraud", "prob_mae_vs_truth"]
    count_cols = ["model", "count_ratio_returned", "count_ratio_failed", "count_ratio_fraud"]
    margin_cols = ["model", "margin_bias_pct", "daily_mape", "daily_mape_normal", "daily_mape_peak"]
    f4 = dict.fromkeys(["macro_f1", "log_loss", "ece_mean", "ece_fraud", "prob_mae_vs_truth"], ".4f")
    f3 = dict.fromkeys(["count_ratio_returned", "count_ratio_failed", "count_ratio_fraud"], ".3f")
    pct = {"margin_bias_pct": "+.2%"} | dict.fromkeys(
        ["daily_mape", "daily_mape_normal", "daily_mape_peak"], ".2%"
    )
    pol = res.policy.copy()
    ci = list(s["margin_minus_risk_rule_ci95"])  # type: ignore[call-overload]
    err = res.margin_error_by_outcome.reset_index(names="outcome")
    err_fmt = dict.fromkeys(res.margin_error_by_outcome.columns, "+,.0f")
    sens = res.conversion_sensitivity.drop(columns=["policy"])
    pol_fmt = {
        "blocked_share_of_cod": ".1%",
        "orders_lost": ",.0f",
        "margin_change": "+,.0f",
        "margin_change_pct": "+.2%",
        "margin_per_order_lost": "+,.1f",
    }
    return f"""# Run report

{s["orders_total"]:,} orders; test window {s["orders_test"]:,} orders over {s["test_days"]} days,
{s["cod_orders_test"]:,} of them cash on delivery. Booster stopped at {s["gbm_rounds"]} rounds
(class-weighted: {s["gbm_weighted_rounds"]}). Realized test margin {s["realized_margin_test"]:,.0f};
true expected margin {s["true_expected_margin_test"]:,.0f}, so the realized total sits
{s["realized_minus_true_expected_sd"]:+.2f} standard deviations from what the true probabilities expect
(one SD of outcome noise is {s["outcome_noise_sd_of_total_pct"]:.2%} of the total).
Runtime {s["runtime_seconds"]}s.

## Classification and calibration (test window)

{_table(res.metrics[model_cols], f4)}

## Predicted / observed outcome counts (1.000 is exact)

{_table(res.metrics[count_cols], f3)}

## Expected vs realized contribution margin (test window)

{_table(res.metrics[margin_cols], pct)}

## Margin error by outcome (expected minus noise-free realized, test window)

{_table(err, err_fmt)}

## COD blocking policy (test window, scored on true probabilities)

{_table(pol, pol_fmt)}

Margin rule minus risk rule at matched volume: {s["margin_minus_risk_rule"]:+,.0f}
(order bootstrap 95% CI {ci[0]:+,.0f} to {ci[1]:+,.0f}).

## Sensitivity to the card-conversion assumption (decisions fixed)

{_table(sens, pol_fmt | {"actual_minus_assumed_conversion": "+.2f"})}
"""
