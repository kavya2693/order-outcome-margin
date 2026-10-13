"""Contribution margin of an order under each of the five outcomes.

The model only supplies probabilities. Turning them into money is a dot product with
this table, which is why the table is kept outside the model and is unit tested.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from order_margin.config import (
    CANCELLED,
    DELIVERED,
    ECON,
    FAILED,
    FRAUD,
    N_CLASSES,
    REMOTE_ZONES,
    RETURNED,
    Economics,
)


def payment_fee(value: np.ndarray, payment: np.ndarray, econ: Economics = ECON) -> np.ndarray:
    return np.select(
        [payment == "cod", payment == "card"],
        [
            econ.cod_fee_flat + econ.cod_fee_rate * value,
            econ.card_fee_flat + econ.card_fee_rate * value,
        ],
        default=econ.wallet_fee_rate * value,
    )


def outcome_margins(
    orders: pd.DataFrame, payment: np.ndarray | None = None, econ: Economics = ECON
) -> np.ndarray:
    """Return an (n_orders, 5) matrix: margin of each order if it ends in each outcome.

    `payment` overrides the order's payment method, which is how the COD policy asks
    "what would this order be worth if it were paid by card".
    """
    value = orders["basket_value"].to_numpy(float)
    cat = orders["category"].to_numpy()
    pay = orders["payment"].to_numpy() if payment is None else np.asarray(payment)
    remote = orders["zone"].isin(REMOTE_ZONES).to_numpy()
    items = orders["n_items"].to_numpy(float)

    gm = pd.Series(cat).map(econ.gross_margin).to_numpy(float)
    loss = pd.Series(cat).map(econ.resale_loss).to_numpy(float)
    cogs = value * (1.0 - gm)
    ship_out = econ.ship_out_base + econ.ship_out_remote * remote + econ.ship_out_per_sqrt_item * np.sqrt(items)
    ship_fee = np.where(value >= econ.free_shipping_threshold, 0.0, econ.shipping_fee)
    fee = payment_fee(value, pay, econ)
    is_cod = pay == "cod"

    m = np.empty((len(orders), N_CLASSES))
    m[:, DELIVERED] = value - cogs + ship_fee - ship_out - fee
    # A returned order earns nothing, pays both shipping legs and loses part of the stock.
    m[:, RETURNED] = -(ship_out + econ.return_ship + econ.return_handling + loss * cogs + fee)
    # Cancelled before dispatch: a prepaid order still pays the flat card fee on the refund.
    m[:, CANCELLED] = -(econ.cancel_cost + np.where(is_cod, 0.0, econ.card_fee_flat))
    # Refused at the door: both legs paid, no cash collected, so no COD fee either.
    m[:, FAILED] = -(
        ship_out * (1.0 + econ.rto_share) + econ.failed_handling + np.where(is_cod, 0.0, econ.card_fee_flat)
    )
    m[:, FRAUD] = -(cogs + ship_out + econ.chargeback_fee + fee)
    return m


def expected_margin(proba: np.ndarray, margins: np.ndarray) -> np.ndarray:
    """Probability-weighted margin per order."""
    return (proba * margins).sum(axis=1)
