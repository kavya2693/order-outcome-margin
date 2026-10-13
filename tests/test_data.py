import numpy as np
import pandas as pd

from order_margin.config import CLASSES
from order_margin.generate import generate


def test_same_seed_same_data() -> None:
    a = generate(seed=5, end="2024-03-31", base_daily=10.0, n_customers=800)
    b = generate(seed=5, end="2024-03-31", base_daily=10.0, n_customers=800)
    pd.testing.assert_frame_equal(a[0], b[0])
    pd.testing.assert_frame_equal(a[1], b[1])


def test_true_probabilities_are_distributions(small) -> None:
    _, truth = small
    for prefix in ("p_", "p_card_"):
        P = truth[[f"{prefix}{c}" for c in CLASSES]].to_numpy()
        assert np.allclose(P.sum(axis=1), 1.0)
        assert (P >= 0).all()


def test_cash_on_delivery_cannot_end_in_a_chargeback(small) -> None:
    orders, truth = small
    cod = orders["payment"] == "cod"
    assert (orders.loc[cod, "outcome"] != "fraud_chargeback").all()
    p = truth.set_index("order_id").loc[orders.loc[cod, "order_id"], "p_fraud_chargeback"]
    assert (p == 0).all()


def test_outcome_mix_and_mess_look_like_a_marketplace(small) -> None:
    orders, _ = small
    share = orders["outcome"].value_counts(normalize=True)
    assert 0.72 < share["delivered"] < 0.86
    assert 0.06 < share["returned"] < 0.13
    assert 0.001 < share["fraud_chargeback"] < 0.01
    assert orders["address_quality"].isna().mean() > 0.02
    assert orders["device_new"].isna().mean() > 0.02
    assert orders["basket_value"].max() > 20 * orders["basket_value"].median()
    daily = orders.groupby(orders["order_ts"].dt.normalize()).size()
    peak = orders.groupby(orders["order_ts"].dt.normalize())["is_peak"].max()
    assert daily[peak == 1].mean() > 1.6 * daily[peak == 0].mean()
