"""Blocking cash on delivery for risky orders, scored on margin against orders lost.

A blocked COD order is not simply lost: some customers pay by card instead. The value
of blocking order i is therefore

    gain_i = conv_i * E[margin | card] - E[margin | COD]

and the order counts as lost with probability (1 - conv_i). The model estimates both
expectations by scoring the same order twice with the payment feature switched.
Scoring a policy uses the generator's true probabilities, never the model's.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from order_margin.config import CANCELLED, COD_TO_CARD_CONVERSION, FAILED, NEW_CUSTOMER_DAYS


def conversion_rate(orders: pd.DataFrame) -> np.ndarray:
    new = orders["account_age_days"].to_numpy() < NEW_CUSTOMER_DAYS
    return np.where(new, COD_TO_CARD_CONVERSION["new"], COD_TO_CARD_CONVERSION["returning"])


@dataclass(frozen=True)
class PolicyResult:
    name: str
    blocked: int
    orders_lost: float
    margin_change: float

    def as_row(self, cod_orders: int, base_margin: float) -> dict[str, object]:
        return {
            "policy": self.name,
            "cod_orders_blocked": self.blocked,
            "blocked_share_of_cod": self.blocked / max(cod_orders, 1),
            "orders_lost": round(self.orders_lost, 1),
            "margin_change": round(self.margin_change, 0),
            "margin_change_pct": self.margin_change / base_margin,
            "margin_per_order_lost": self.margin_change / self.orders_lost if self.orders_lost else np.nan,
        }


def score_policy(
    name: str, block: np.ndarray, conv: np.ndarray, em_cod_true: np.ndarray, em_card_true: np.ndarray
) -> PolicyResult:
    """True expected change in margin from blocking the flagged COD orders."""
    gain = conv * em_card_true - em_cod_true
    return PolicyResult(
        name=name,
        blocked=int(block.sum()),
        orders_lost=float(((1.0 - conv) * block).sum()),
        margin_change=float((gain * block).sum()),
    )


def risk_score(P_cod: np.ndarray) -> np.ndarray:
    """What a risk team usually ranks on: chance the parcel does not end in cash."""
    return np.asarray(P_cod[:, FAILED] + P_cod[:, CANCELLED])


def threshold_for_share(score: np.ndarray, share: float) -> float:
    if share <= 0:
        return float("inf")
    return float(np.quantile(score, 1.0 - share))


def frontier(
    score: np.ndarray, conv: np.ndarray, em_cod_true: np.ndarray, em_card_true: np.ndarray, n: int = 40
) -> pd.DataFrame:
    """Margin change against orders lost as the block threshold sweeps from none to all."""
    gain = conv * em_card_true - em_cod_true
    lost = 1.0 - conv
    order = np.argsort(-score, kind="stable")
    cum_gain = np.r_[0.0, np.cumsum(gain[order])]
    cum_lost = np.r_[0.0, np.cumsum(lost[order])]
    # Dense near zero, where the useful policies sit, and linear out to blocking everything.
    k = np.unique(np.r_[0, np.geomspace(1, len(score), n), np.linspace(0, len(score), n + 1)].astype(int))
    return pd.DataFrame({"blocked": k, "orders_lost": cum_lost[k], "margin_change": cum_gain[k]})
