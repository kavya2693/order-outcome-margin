import pandas as pd

from order_margin.features import FEATURES, build_features, customer_history


def _history(outcomes: list[str], days: list[int]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "customer_id": [1] * len(days),
            "order_ts": pd.to_datetime("2025-01-01") + pd.to_timedelta(days, unit="D"),
            "outcome": outcomes,
            "payment": ["cod"] * len(days),
        }
    )


def test_history_only_counts_orders_old_enough_to_be_resolved() -> None:
    o = _history(["returned", "returned", "delivered", "delivered"], [0, 5, 10, 20])
    h = customer_history(o)
    assert h["prior_orders"].tolist() == [0, 1, 2, 3]
    # Day 10 sees nothing resolved (day 0 is only 10 days back); day 20 sees days 0 and 5.
    assert h["prior_resolved"].tolist() == [0, 0, 0, 2]


def test_unresolved_outcome_cannot_change_features() -> None:
    a = _history(["delivered", "delivered", "delivered"], [0, 30, 35])
    b = a.copy()
    b.loc[1, "outcome"] = "failed_delivery"  # order on day 30 is unresolved at day 35
    pd.testing.assert_frame_equal(customer_history(a), customer_history(b))


def test_history_is_aligned_to_input_order() -> None:
    o = _history(["returned", "delivered", "delivered"], [0, 20, 40]).iloc[::-1]
    h = customer_history(o)
    assert h.loc[2, "prior_orders"] == 2
    assert h.loc[0, "prior_orders"] == 0


def test_feature_frame_has_every_column(small) -> None:
    orders, _ = small
    X = build_features(orders.head(500))
    assert list(X.columns) == FEATURES
    assert X["address_quality"].isna().any()
