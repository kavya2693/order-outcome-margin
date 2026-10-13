"""End to end: features, models, calibration, margin forecast and COD policy."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from order_margin.calibration import (
    IsotonicCalibrator,
    PlattCalibrator,
    classwise_ece,
    count_ratio,
    log_loss,
    macro_f1,
)
from order_margin.config import (
    CALIB_END,
    CLASSES,
    EARLY_STOP_END,
    FAILED,
    FRAUD,
    RETURNED,
    TRAIN_END,
)
from order_margin.economics import expected_margin, outcome_margins
from order_margin.features import build_features, with_payment
from order_margin.models import GBMModel, LogitModel, PriorModel
from order_margin.policy import (
    conversion_rate,
    frontier,
    risk_score,
    score_policy,
    threshold_for_share,
)

Log = Callable[[str], None]


@dataclass
class Results:
    metrics: pd.DataFrame
    daily: pd.DataFrame
    policy: pd.DataFrame
    frontier: pd.DataFrame
    summary: dict[str, object]
    margin_error_by_outcome: pd.DataFrame = field(default_factory=pd.DataFrame)
    conversion_sensitivity: pd.DataFrame = field(default_factory=pd.DataFrame)
    reliability: dict[str, np.ndarray] = field(default_factory=dict)
    y_test: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=int))


def load(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    orders = pd.read_csv(data_dir / "orders.csv.gz", parse_dates=["order_ts"])
    truth = pd.read_csv(data_dir / "truth" / "order_truth.csv.gz")
    return orders, truth


def split_masks(orders: pd.DataFrame) -> dict[str, np.ndarray]:
    d = orders["order_ts"].dt.normalize()
    return {
        "train": (d <= TRAIN_END).to_numpy(),
        "early_stop": ((d > TRAIN_END) & (d <= EARLY_STOP_END)).to_numpy(),
        "calib": ((d > EARLY_STOP_END) & (d <= CALIB_END)).to_numpy(),
        "test": (d > CALIB_END).to_numpy(),
    }


def _daily_errors(
    em: np.ndarray, realized: np.ndarray, day: np.ndarray, peak: np.ndarray
) -> dict[str, float]:
    df = pd.DataFrame({"day": day, "em": em, "real": realized, "peak": peak})
    g = df.groupby("day").agg(em=("em", "sum"), real=("real", "sum"), peak=("peak", "max"))
    ape = (g["em"] - g["real"]).abs() / g["real"].abs()
    return {
        "margin_bias_pct": float((g["em"].sum() - g["real"].sum()) / g["real"].sum()),
        "daily_mape": float(ape.mean()),
        "daily_mape_normal": float(ape[g["peak"] == 0].mean()),
        "daily_mape_peak": float(ape[g["peak"] == 1].mean()) if (g["peak"] == 1).any() else float("nan"),
    }


def run(
    orders: pd.DataFrame,
    truth: pd.DataFrame,
    log: Log = print,
    max_rounds: int = 3000,
) -> Results:
    t0 = time.time()
    orders = orders.reset_index(drop=True)
    truth = truth.set_index("order_id").loc[orders["order_id"]].reset_index()
    y = pd.Categorical(orders["outcome"], categories=list(CLASSES)).codes.astype(int)
    X = build_features(orders)
    m = split_masks(orders)
    log(
        "split  "
        + "  ".join(f"{k}={int(v.sum()):,}" for k, v in m.items())
        + f"  ({time.time() - t0:.0f}s features)"
    )
    fit_mask = m["train"] | m["early_stop"]

    prior = PriorModel().fit(X[fit_mask], y[fit_mask])
    logit = LogitModel().fit(X[m["train"]], y[m["train"]])
    log(f"logistic fitted ({time.time() - t0:.0f}s)")
    gbm = GBMModel(max_rounds=max_rounds).fit(X[m["train"]], y[m["train"]], X[m["early_stop"]], y[m["early_stop"]])
    log(f"gbm fitted, {gbm.best_iteration} rounds ({time.time() - t0:.0f}s)")
    gbmw = GBMModel(class_weighted=True, max_rounds=max_rounds).fit(
        X[m["train"]], y[m["train"]], X[m["early_stop"]], y[m["early_stop"]]
    )
    log(f"class-weighted gbm fitted, {gbmw.best_iteration} rounds ({time.time() - t0:.0f}s)")

    Xc, yc, Xt, yt = X[m["calib"]], y[m["calib"]], X[m["test"]], y[m["test"]]
    raw_c = {"logit": logit.predict_proba(Xc), "gbm": gbm.predict_proba(Xc), "gbmw": gbmw.predict_proba(Xc)}
    raw_t = {"logit": logit.predict_proba(Xt), "gbm": gbm.predict_proba(Xt), "gbmw": gbmw.predict_proba(Xt)}
    iso = {k: IsotonicCalibrator().fit(v, yc) for k, v in raw_c.items()}
    platt = {k: PlattCalibrator().fit(v, yc) for k, v in raw_c.items()}

    p_cols = [f"p_{c}" for c in CLASSES]
    P_true_t = truth.loc[m["test"], p_cols].to_numpy()
    variants: dict[str, np.ndarray] = {
        "class priors": prior.predict_proba(Xt),
        "logistic, raw": raw_t["logit"],
        "logistic + isotonic": iso["logit"].transform(raw_t["logit"]),
        "gbm, raw": raw_t["gbm"],
        "gbm + Platt": platt["gbm"].transform(raw_t["gbm"]),
        "gbm + isotonic": iso["gbm"].transform(raw_t["gbm"]),
        "gbm class-weighted, raw": raw_t["gbmw"],
        "gbm class-weighted + isotonic": iso["gbmw"].transform(raw_t["gbmw"]),
        "true probabilities (ceiling)": P_true_t,
    }

    ot = orders.loc[m["test"]].reset_index(drop=True)
    margins_t = outcome_margins(ot)
    realized = ot["realized_margin"].to_numpy()
    day = ot["order_ts"].dt.normalize().to_numpy()
    peak = ot["is_peak"].to_numpy()

    rows = []
    for name, P in variants.items():
        ece = classwise_ece(P, yt)
        ratio = count_ratio(P, yt)
        em = expected_margin(P, margins_t)
        rows.append(
            {
                "model": name,
                "macro_f1": macro_f1(P, yt),
                "log_loss": log_loss(P, yt),
                "ece_mean": float(ece.mean()),
                "ece_fraud": float(ece[FRAUD]),
                "count_ratio_returned": float(ratio[RETURNED]),
                "count_ratio_failed": float(ratio[FAILED]),
                "count_ratio_fraud": float(ratio[FRAUD]),
                "prob_mae_vs_truth": float(np.abs(P - P_true_t).mean()),
                **_daily_errors(em, realized, day, peak),
            }
        )
    metrics = pd.DataFrame(rows)

    # Where the margin error comes from: for each outcome, predicted minus actual
    # occurrences, each weighted by what that outcome costs on that order.
    onehot = np.eye(len(CLASSES))[yt]
    decomp = pd.DataFrame(
        {
            name: ((variants[name] - onehot) * margins_t).sum(axis=0)
            for name in ["logistic + isotonic", "gbm + isotonic", "true probabilities (ceiling)"]
        },
        index=list(CLASSES),
    )
    decomp.loc["total"] = decomp.sum()
    log(f"metrics done ({time.time() - t0:.0f}s)")

    daily = pd.DataFrame({"day": day, "realized": realized, "peak": peak})
    for name in ["class priors", "gbm + isotonic", "gbm class-weighted, raw", "true probabilities (ceiling)"]:
        daily[name] = expected_margin(variants[name], margins_t)
    daily = daily.groupby("day").agg({c: ("max" if c == "peak" else "sum") for c in daily.columns[1:]})

    # COD policy on the test window. Decisions use the calibrated booster; scoring uses truth.
    cod = (ot["payment"] == "cod").to_numpy()
    oc = ot.loc[cod].reset_index(drop=True)
    conv = conversion_rate(oc)
    margins_cod = outcome_margins(oc)
    margins_card = outcome_margins(oc, payment=np.full(len(oc), "card"))
    em_cod_true = expected_margin(P_true_t[cod], margins_cod)
    card_cols = [f"p_card_{c}" for c in CLASSES]
    em_card_true = expected_margin(truth.loc[m["test"], card_cols].to_numpy()[cod], margins_card)

    Xt_cod = Xt[cod]
    Xt_card = with_payment(Xt_cod, "card")

    def gain_hat(model: GBMModel, cal: IsotonicCalibrator | None) -> np.ndarray:
        pc, pk = model.predict_proba(Xt_cod), model.predict_proba(Xt_card)
        if cal is not None:
            pc, pk = cal.transform(pc), cal.transform(pk)
        return np.asarray(conv * expected_margin(pk, margins_card) - expected_margin(pc, margins_cod))

    g_iso = gain_hat(gbm, iso["gbm"])
    g_raw = gain_hat(gbm, None)
    g_w = gain_hat(gbmw, None)
    g_true = conv * em_card_true - em_cod_true
    risk = risk_score(iso["gbm"].transform(gbm.predict_proba(Xt_cod)))

    # The risk rule gets the same block rate the margin rule chose on the calibration
    # window, so the two are compared at equal volume without peeking at the test set.
    calib_cod = (orders.loc[m["calib"], "payment"] == "cod").to_numpy()
    oc_c = orders.loc[m["calib"]].reset_index(drop=True).loc[calib_cod].reset_index(drop=True)
    Xc_cod = Xc[calib_cod]
    conv_c = conversion_rate(oc_c)
    pc_c = iso["gbm"].transform(gbm.predict_proba(Xc_cod))
    pk_c = iso["gbm"].transform(gbm.predict_proba(with_payment(Xc_cod, "card")))
    g_c = conv_c * expected_margin(pk_c, outcome_margins(oc_c, payment=np.full(len(oc_c), "card")))
    g_c = g_c - expected_margin(pc_c, outcome_margins(oc_c))
    share = float((g_c > 0).mean())
    risk_t = threshold_for_share(risk_score(pc_c), share)

    new_big = (oc["account_age_days"].to_numpy() < 30) & (oc["basket_value"].to_numpy() > 300)
    policies = [
        ("no blocking", np.zeros(len(oc), bool)),
        ("block every COD order", np.ones(len(oc), bool)),
        ("rule of thumb: new customer and basket > 300", new_big),
        (f"risk score, same block rate as margin rule on calib ({share:.1%})", risk >= risk_t),
        ("margin rule, uncalibrated gbm", g_raw > 0),
        ("margin rule, class-weighted gbm", g_w > 0),
        ("margin rule, gbm + isotonic", g_iso > 0),
        ("margin rule, true probabilities (ceiling)", g_true > 0),
    ]
    base_margin = float(expected_margin(P_true_t, margins_t).sum())
    policy = pd.DataFrame(
        [
            score_policy(n, b, conv, em_cod_true, em_card_true).as_row(len(oc), base_margin)
            for n, b in policies
        ]
    )
    fr = pd.concat(
        [
            frontier(g_iso, conv, em_cod_true, em_card_true).assign(ranking="margin gain, gbm + isotonic"),
            frontier(risk, conv, em_cod_true, em_card_true).assign(ranking="risk score, gbm + isotonic"),
            frontier(g_true, conv, em_cod_true, em_card_true).assign(ranking="margin gain, true probabilities"),
        ]
    )

    # The conversion table is an assumption. Keep the decisions fixed and score them as
    # if fewer (or more) blocked customers actually switched to card.
    block_iso = g_iso > 0
    sens = pd.DataFrame(
        [
            {
                "actual_minus_assumed_conversion": d,
                **score_policy(
                    "margin rule, gbm + isotonic",
                    block_iso,
                    np.clip(conv + d, 0.0, 1.0),
                    em_cod_true,
                    em_card_true,
                ).as_row(len(oc), base_margin),
            }
            for d in (-0.30, -0.20, -0.10, 0.0, 0.10)
        ]
    )

    # Order-level bootstrap of the paired difference between the margin rule and the
    # risk rule at matched volume: is the gap bigger than which orders happened to arrive?
    rng = np.random.default_rng(0)
    gain = conv * em_card_true - em_cod_true
    diff = gain * block_iso - gain * (risk >= risk_t)
    boot = np.array([diff[rng.integers(0, len(diff), len(diff))].sum() for _ in range(1000)])
    lo, hi = np.percentile(boot, [2.5, 97.5])
    log(f"policy done ({time.time() - t0:.0f}s)")

    realized_total = float(realized.sum())
    # Spread of the realized total if the true probabilities were known exactly: the
    # floor no model can get under, because outcomes are still random.
    em_true = expected_margin(P_true_t, margins_t)
    var = (P_true_t * margins_t**2).sum(axis=1) - em_true**2
    noise_sd = float(np.sqrt(var.sum()))
    summary: dict[str, object] = {
        "orders_total": len(orders),
        "orders_test": int(m["test"].sum()),
        "cod_orders_test": len(oc),
        "test_days": int(daily.shape[0]),
        "gbm_rounds": gbm.best_iteration,
        "gbm_weighted_rounds": gbmw.best_iteration,
        "realized_margin_test": realized_total,
        "true_expected_margin_test": base_margin,
        "realized_minus_true_expected_sd": (realized_total - base_margin) / noise_sd,
        "outcome_noise_sd_of_total_pct": noise_sd / base_margin,
        "outcome_share_test": {c: float((yt == k).mean()) for k, c in enumerate(CLASSES)},
        "margin_rule_block_share_calib": share,
        "margin_minus_risk_rule": float(diff.sum()),
        "margin_minus_risk_rule_ci95": [float(lo), float(hi)],
        "runtime_seconds": round(time.time() - t0, 1),
    }
    reliability = {
        name: variants[name]
        for name in ["gbm, raw", "gbm + Platt", "gbm + isotonic", "gbm class-weighted, raw"]
    }
    return Results(metrics, daily, policy, fr, summary, decomp, sens, reliability, yt)


def write(res: Results, out_dir: Path) -> None:
    from order_margin.plots import plot_daily, plot_frontier, plot_reliability
    from order_margin.report import render

    out_dir.mkdir(parents=True, exist_ok=True)
    res.metrics.round(4).to_csv(out_dir / "metrics.csv", index=False)
    res.daily.round(1).to_csv(out_dir / "daily_margin.csv")
    res.policy.round(4).to_csv(out_dir / "policy.csv", index=False)
    res.conversion_sensitivity.round(4).to_csv(out_dir / "conversion_sensitivity.csv", index=False)
    res.margin_error_by_outcome.round(0).to_csv(out_dir / "margin_error_by_outcome.csv")
    res.frontier.round(1).to_csv(out_dir / "policy_frontier.csv", index=False)
    (out_dir / "results.json").write_text(json.dumps(res.summary, indent=2, default=str) + "\n")
    plot_reliability(res.reliability, res.y_test, out_dir / "reliability.png")
    plot_daily(res.daily, out_dir / "daily_margin.png")
    plot_frontier(res.frontier, res.policy, out_dir / "policy_frontier.png")
    (out_dir / "report.md").write_text(render(res))
