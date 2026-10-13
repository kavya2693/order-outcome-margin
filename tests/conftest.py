from __future__ import annotations

import pandas as pd
import pytest

from order_margin.generate import generate
from order_margin.pipeline import Results, run


@pytest.fixture(scope="session")
def small() -> tuple[pd.DataFrame, pd.DataFrame]:
    return generate(seed=11, base_daily=30.0, n_customers=9000)


@pytest.fixture(scope="session")
def results(small: tuple[pd.DataFrame, pd.DataFrame]) -> Results:
    orders, truth = small
    return run(orders, truth, log=lambda _: None, max_rounds=300)
