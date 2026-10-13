"""Model features, including customer history that respects when outcomes become known.

A return or a failed delivery is only known days after the order is placed. Counting it
as history for an order placed the next morning would leak the label, so history rates
use only orders placed at least `RESOLVE_DAYS` earlier.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from order_margin.config import CATEGORIES, PAYMENTS, ZONES

RESOLVE_DAYS = 14
PRIOR_STRENGTH = 5.0  # pseudo-orders pulling a thin history towards the population rate
# Fixed long-run rates for that pull. Computing them from the frame itself would let the
# test window's outcomes leak into every training row's features.
POPULATION_RATE = {"returned": 0.09, "failed_delivery": 0.05, "cancelled": 0.055}

NUMERIC = [
    "log_value",
    "n_items",
    "discount_pct",
    "coupon_used",
    "promised_days",
    "log_account_age",
    "address_quality",
    "device_new",
    "phone_verified",
    "is_peak",
    "is_ramadan",
    "hour",
    "dow",
    "prior_orders",
    "prior_resolved",
    "prior_return_rate",
    "prior_failed_rate",
    "prior_cancel_rate",
    "prior_cod_share",
    "days_since_last",
]
CATEGORICAL = ["category", "payment", "zone"]
FEATURES = NUMERIC + CATEGORICAL
CATEGORY_LEVELS = {"category": list(CATEGORIES), "payment": list(PAYMENTS), "zone": list(ZONES)}


def customer_history(orders: pd.DataFrame, resolve_days: int = RESOLVE_DAYS) -> pd.DataFrame:
    """History columns aligned to `orders.index`."""
    o = orders.sort_values(["customer_id", "order_ts"], kind="stable")
    cust = o["customer_id"].to_numpy(np.int64)
    t = (o["order_ts"] - pd.Timestamp("2000-01-01")).dt.total_seconds().to_numpy() / 86400.0
    n = len(o)
    idx = np.arange(n)
    first = np.r_[True, cust[1:] != cust[:-1]]
    group_start = np.maximum.accumulate(np.where(first, idx, 0))

    # One sortable key per (customer, time); customers are 1e5 days apart.
    key = cust * 1e5 + t
    resolved_end = np.searchsorted(key, cust * 1e5 + t - resolve_days, side="right")
    resolved_end = np.maximum(resolved_end, group_start)
    resolved = resolved_end - group_start

    def prior_count(flag: np.ndarray) -> np.ndarray:
        c = np.r_[0, np.cumsum(flag)]
        return c[resolved_end] - c[group_start]

    outcome = o["outcome"].to_numpy()
    cod = (o["payment"].to_numpy() == "cod").astype(float)

    def rate(name: str) -> np.ndarray:
        hits = prior_count((outcome == name).astype(float))
        return (hits + PRIOR_STRENGTH * POPULATION_RATE[name]) / (resolved + PRIOR_STRENGTH)

    c_cod = np.r_[0, np.cumsum(cod)]
    prior_orders = idx - group_start
    with np.errstate(invalid="ignore", divide="ignore"):
        cod_share = np.where(prior_orders > 0, (c_cod[idx] - c_cod[group_start]) / prior_orders, np.nan)
    gap = np.where(first, np.nan, t - np.r_[np.nan, t[:-1]])

    hist = pd.DataFrame(
        {
            "prior_orders": prior_orders,
            "prior_resolved": resolved,
            "prior_return_rate": rate("returned"),
            "prior_failed_rate": rate("failed_delivery"),
            "prior_cancel_rate": rate("cancelled"),
            "prior_cod_share": cod_share,
            "days_since_last": gap,
        },
        index=o.index,
    )
    return hist.reindex(orders.index)


def build_features(orders: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=orders.index)
    X["log_value"] = np.log1p(orders["basket_value"])
    X["log_account_age"] = np.log1p(orders["account_age_days"].clip(lower=0))
    for col in [
        "n_items",
        "discount_pct",
        "coupon_used",
        "promised_days",
        "address_quality",
        "device_new",
        "phone_verified",
        "is_peak",
        "is_ramadan",
    ]:
        X[col] = orders[col].astype(float)
    X["hour"] = orders["order_ts"].dt.hour
    X["dow"] = orders["order_ts"].dt.dayofweek
    X = X.join(customer_history(orders))
    for col in CATEGORICAL:
        X[col] = pd.Categorical(orders[col], categories=CATEGORY_LEVELS[col])
    return X[FEATURES]


def with_payment(X: pd.DataFrame, payment: str) -> pd.DataFrame:
    """Same orders with the payment method switched, for counterfactual scoring."""
    Xc = X.copy()
    Xc["payment"] = pd.Categorical([payment] * len(Xc), categories=CATEGORY_LEVELS["payment"])
    return Xc
