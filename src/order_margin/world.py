"""The outcome process the generator samples from.

Outcome probabilities depend on customer traits the model never sees (a tendency to
return, to refuse at the door, to cancel, and whether the account is a fraud account).
The model has to infer them from order history, which is what makes the problem hard.
Fraud chargebacks need a card network, so COD orders cannot end that way.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from order_margin.config import CANCELLED, FAILED, FRAUD, N_CLASSES, REMOTE_ZONES, RETURNED

CATEGORY_RETURN = {"fashion": 0.9, "electronics": -0.2, "home": -0.1, "beauty": -1.2, "grocery": -2.8}


def true_logits(df: pd.DataFrame, payment: np.ndarray | None = None) -> np.ndarray:
    pay = df["payment"].to_numpy() if payment is None else np.asarray(payment)
    cod = (pay == "cod").astype(float)
    card = (pay == "card").astype(float)
    wallet = (pay == "wallet").astype(float)
    cat = df["category"].to_numpy()
    fashion = (cat == "fashion").astype(float)
    electronics = (cat == "electronics").astype(float)
    remote = df["zone"].isin(REMOTE_ZONES).to_numpy(float)
    lv = np.log(df["basket_value"].to_numpy(float) / 150.0)
    lv_pos = np.clip(lv, 0.0, None)
    new = (df["account_age_days"].to_numpy(float) < 30).astype(float)
    peak = df["is_peak"].to_numpy(float)
    ramadan = df["is_ramadan"].to_numpy(float)
    promised = df["promised_days"].to_numpy(float)
    addr = df["addr_quality_true"].to_numpy(float)
    discount = df["discount_pct"].to_numpy(float)
    items = df["n_items"].to_numpy(float)

    z = np.zeros((len(df), N_CLASSES))
    z[:, RETURNED] = (
        -2.55
        + pd.Series(cat).map(CATEGORY_RETURN).to_numpy(float)
        + 0.9 * df["ret_trait"].to_numpy(float)
        + 1.4 * discount
        # Bracketing: several sizes of the same item, most of which come back.
        + 0.45 * fashion * (items >= 3)
        + 0.15 * lv
        - 0.3 * cod
        + 0.35 * peak
    )
    z[:, CANCELLED] = (
        -3.3
        + 0.65 * cod
        + 0.3 * (promised - 2.0)
        + 0.8 * df["cancel_trait"].to_numpy(float)
        + 0.5 * new
        + 0.35 * lv_pos * cod
        + 0.25 * peak
    )
    z[:, FAILED] = (
        -4.6
        + 1.7 * cod
        + 0.9 * remote
        + 2.0 * (0.6 - addr)
        + 0.95 * df["refusal_trait"].to_numpy(float)
        + 0.6 * new * cod
        + 0.45 * lv_pos * cod
        + 0.2 * (promised - 2.0)
        + 0.3 * ramadan
    )
    fraud = (
        -7.7
        + 4.6 * df["fraudster"].to_numpy(float)
        + 1.0 * electronics
        + 0.7 * lv_pos
        + 0.9 * df["device_new_true"].to_numpy(float)
        + 0.8 * (1.0 - df["phone_verified"].to_numpy(float))
        + 0.6 * new
        - 0.8 * wallet
    )
    z[:, FRAUD] = np.where(card + wallet > 0, fraud, -np.inf)
    return z


def true_proba(df: pd.DataFrame, payment: np.ndarray | None = None) -> np.ndarray:
    z = true_logits(df, payment)
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)
