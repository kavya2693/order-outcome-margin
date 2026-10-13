import numpy as np
import pandas as pd

from order_margin.config import CANCELLED, DELIVERED, FAILED, FRAUD, N_CLASSES, RETURNED
from order_margin.economics import expected_margin, outcome_margins


def _orders(payment: str = "cod") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "basket_value": [250.0, 60.0],
            "category": ["electronics", "fashion"],
            "payment": [payment, payment],
            "zone": ["metro_a", "remote_north"],
            "n_items": [1, 3],
        }
    )


def test_certain_outcome_gives_that_outcomes_margin() -> None:
    m = outcome_margins(_orders())
    for k in range(N_CLASSES):
        onehot = np.zeros((2, N_CLASSES))
        onehot[:, k] = 1.0
        assert np.allclose(expected_margin(onehot, m), m[:, k])


def test_only_delivery_makes_money_and_fraud_costs_most() -> None:
    m = outcome_margins(_orders("card"))
    assert (m[:, DELIVERED] > 0).all()
    for k in (RETURNED, CANCELLED, FAILED, FRAUD):
        assert (m[:, k] < 0).all()
    assert (m[:, FRAUD] < m[:, RETURNED]).all()


def test_switching_payment_only_moves_fee_dependent_outcomes() -> None:
    o = _orders("cod")
    cod = outcome_margins(o)
    card = outcome_margins(o, payment=np.array(["card", "card"]))
    # Refused COD parcels never collect cash, so no COD fee; a refused prepaid one pays the refund fee.
    assert np.allclose(card[:, FAILED] - cod[:, FAILED], -1.0)
    assert not np.allclose(card[:, DELIVERED], cod[:, DELIVERED])
