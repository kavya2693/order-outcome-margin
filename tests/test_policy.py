import numpy as np
import pandas as pd

from order_margin.policy import conversion_rate, frontier, score_policy


def test_blocking_nothing_changes_nothing() -> None:
    conv = np.array([0.6, 0.4])
    r = score_policy("none", np.zeros(2, bool), conv, np.array([10.0, -30.0]), np.array([12.0, 5.0]))
    assert r.blocked == 0 and r.orders_lost == 0 and r.margin_change == 0


def test_block_value_accounts_for_customers_who_walk_away() -> None:
    conv = np.array([0.5])
    # COD worth -30 in expectation, card worth +20: blocking keeps half the orders at +20.
    r = score_policy("one", np.ones(1, bool), conv, np.array([-30.0]), np.array([20.0]))
    assert np.isclose(r.margin_change, 0.5 * 20 + 30)
    assert np.isclose(r.orders_lost, 0.5)


def test_blocking_a_good_cod_order_loses_money_even_if_card_is_better() -> None:
    r = score_policy("x", np.ones(1, bool), np.array([0.6]), np.array([40.0]), np.array([45.0]))
    assert r.margin_change < 0


def test_frontier_runs_from_nothing_to_everything() -> None:
    rng = np.random.default_rng(0)
    em_cod, em_card = rng.normal(20, 30, 500), rng.normal(25, 10, 500)
    conv = np.full(500, 0.5)
    f = frontier(rng.random(500), conv, em_cod, em_card)
    assert f.iloc[0]["margin_change"] == 0
    assert np.isclose(f.iloc[-1]["margin_change"], (conv * em_card - em_cod).sum())
    assert np.isclose(f.iloc[-1]["orders_lost"], 250.0)


def test_new_customers_convert_less() -> None:
    conv = conversion_rate(pd.DataFrame({"account_age_days": [3, 400]}))
    assert conv[0] < conv[1]
