"""Three models of increasing capacity, all exposing `predict_proba(X) -> (n, 5)`.

- class priors: what a finance team does today when it applies last quarter's
  return and failure rates to every order;
- multinomial logistic regression on one-hot and imputed features;
- LightGBM multiclass, optionally with inverse-frequency class weights. The weighted
  variant exists because it is the usual fix people reach for when macro-F1 is low.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from order_margin.config import N_CLASSES
from order_margin.features import CATEGORICAL, NUMERIC


class ProbaModel(Protocol):
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray: ...


@dataclass
class PriorModel:
    prior: np.ndarray = field(default_factory=lambda: np.full(N_CLASSES, 1.0 / N_CLASSES))

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> PriorModel:
        counts = np.bincount(y, minlength=N_CLASSES).astype(float)
        self.prior = counts / counts.sum()
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return np.tile(self.prior, (len(X), 1))


@dataclass
class LogitModel:
    pipe: Pipeline | None = None

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> LogitModel:
        pre = ColumnTransformer(
            [
                (
                    "num",
                    make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()),
                    NUMERIC,
                ),
                ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
            ]
        )
        self.pipe = make_pipeline(pre, LogisticRegression(max_iter=400, C=1.0))
        self.pipe.fit(X, y)
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        assert self.pipe is not None
        return np.asarray(self.pipe.predict_proba(X))


@dataclass
class GBMModel:
    class_weighted: bool = False
    params: dict[str, object] = field(
        default_factory=lambda: {
            "objective": "multiclass",
            "num_class": N_CLASSES,
            "learning_rate": 0.03,
            "num_leaves": 15,
            "min_data_in_leaf": 200,
            "feature_fraction": 0.85,
            "bagging_fraction": 0.85,
            "bagging_freq": 1,
            "lambda_l2": 1.0,
            "num_threads": 4,
            "verbose": -1,
            "seed": 7,
        }
    )
    # Chosen from four settings on the early-stopping and calibration windows, not the test window.
    max_rounds: int = 3000
    booster: lgb.Booster | None = None
    best_iteration: int = 0

    def _weights(self, y: np.ndarray) -> np.ndarray | None:
        if not self.class_weighted:
            return None
        counts = np.bincount(y, minlength=N_CLASSES).astype(float)
        w = len(y) / (N_CLASSES * np.maximum(counts, 1.0))
        return np.asarray(w[y])

    def fit(self, X: pd.DataFrame, y: np.ndarray, X_val: pd.DataFrame, y_val: np.ndarray) -> GBMModel:
        train = lgb.Dataset(X, y, weight=self._weights(y), categorical_feature=CATEGORICAL)
        val = lgb.Dataset(X_val, y_val, weight=self._weights(y_val), reference=train)
        self.booster = lgb.train(
            self.params,
            train,
            num_boost_round=self.max_rounds,
            valid_sets=[val],
            callbacks=[lgb.early_stopping(100, verbose=False)],
        )
        self.best_iteration = int(self.booster.best_iteration or self.max_rounds)
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        assert self.booster is not None
        return np.asarray(self.booster.predict(X, num_iteration=self.best_iteration))
