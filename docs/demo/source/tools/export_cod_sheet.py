"""Re-run the repo's own model for ONE sale-week day and export the COD decision sheet.

Same data, seed, features, LightGBM settings, time split and isotonic calibrator as
`make run` (src/order_margin/pipeline.py), then applies the margin rule from policy.py to
the cash-on-delivery orders placed on 2025-11-24, a day of the November sale week:

    gain = conversion x E[margin | card] - E[margin | COD]   -> hide COD when gain > 0

The decision uses the calibrated booster; the day's realised value of the decisions is
scored on the generator's true probabilities, exactly as pipeline.py scores the policy.
As a consistency check it also re-scores the whole test window and prints the number of
blocked COD orders (outputs/policy.csv says 5,498).

Run:  cd <repo> && PYTHONPATH=src .venv/bin/python <this file> <out.json>
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from order_margin.calibration import IsotonicCalibrator
from order_margin.config import CLASSES, FAILED
from order_margin.economics import expected_margin, outcome_margins
from order_margin.features import build_features, with_payment
from order_margin.models import GBMModel
from order_margin.pipeline import load, split_masks
from order_margin.policy import conversion_rate, risk_score

DAY = "2025-11-24"

orders, truth = load(Path("data"))
orders = orders.reset_index(drop=True)
truth = truth.set_index("order_id").loc[orders["order_id"]].reset_index()
y = pd.Categorical(orders["outcome"], categories=list(CLASSES)).codes.astype(int)
X = build_features(orders)
m = split_masks(orders)

gbm = GBMModel().fit(X[m["train"]], y[m["train"]], X[m["early_stop"]], y[m["early_stop"]])
iso = IsotonicCalibrator().fit(gbm.predict_proba(X[m["calib"]]), y[m["calib"]])
print("gbm rounds", gbm.best_iteration)

p_cols = [f"p_{c}" for c in CLASSES]
card_cols = [f"p_card_{c}" for c in CLASSES]


def score(mask: np.ndarray) -> pd.DataFrame:
    """Margin-rule inputs for the COD orders selected by `mask`."""
    sel = mask & (orders["payment"] == "cod").to_numpy()
    oc = orders.loc[sel].reset_index(drop=True)
    x_cod = X[sel]
    pc = iso.transform(gbm.predict_proba(x_cod))
    pk = iso.transform(gbm.predict_proba(with_payment(x_cod, "card")))
    conv = conversion_rate(oc)
    m_cod = outcome_margins(oc)
    m_card = outcome_margins(oc, payment=np.full(len(oc), "card"))
    em_cod = expected_margin(pc, m_cod)
    em_card = expected_margin(pk, m_card)
    gain = conv * em_card - em_cod
    t_cod = expected_margin(truth.loc[sel, p_cols].to_numpy(), m_cod)
    t_card = expected_margin(truth.loc[sel, card_cols].to_numpy(), m_card)
    return oc.assign(
        p_refuse=pc[:, FAILED],
        risk=risk_score(pc),
        conv=conv,
        em_cod=em_cod,
        em_card=em_card,
        gain=gain,
        block=gain > 0,
        true_gain=conv * t_card - t_cod,
    )


test = score(m["test"])
print("test-window COD orders", len(test), "blocked", int(test["block"].sum()))

day = orders["order_ts"].dt.normalize() == pd.Timestamp(DAY)
d = score(day.to_numpy())
all_day = orders.loc[day].reset_index(drop=True)
P_all = iso.transform(gbm.predict_proba(X[day.to_numpy()]))
em_all = expected_margin(P_all, outcome_margins(all_day))

rows = [
    {
        "order_id": int(r.order_id),
        "zone": r.zone,
        "category": r.category,
        "basket": round(float(r.basket_value), 0),
        "account_age_days": int(r.account_age_days),
        "p_refuse": round(float(r.p_refuse), 3),
        "risk": round(float(r.risk), 3),
        "conv": float(r.conv),
        "em_cod": round(float(r.em_cod), 1),
        "em_card": round(float(r.em_card), 1),
        "gain": round(float(r.gain), 1),
        "block": bool(r.block),
    }
    for r in d.itertuples()
]
blocked = d[d["block"]]
out = {
    "day": DAY,
    "is_peak": int(all_day["is_peak"].max()),
    "orders": len(all_day),
    "cod_orders": len(d),
    "blocked": int(d["block"].sum()),
    "kept": int((~d["block"]).sum()),
    "expected_orders_lost": round(float((1 - blocked["conv"]).sum()), 1),
    "day_true_gain": round(float(blocked["true_gain"].sum()), 0),
    "day_model_gain": round(float(blocked["gain"].sum()), 0),
    "day_expected_margin": round(float(em_all.sum()), 0),
    "day_realized_margin": round(float(all_day["realized_margin"].sum()), 0),
    "risk_top_decile_kept": int(((d["risk"] >= d["risk"].quantile(0.9)) & ~d["block"]).sum()),
    "test_window_blocked": int(test["block"].sum()),
    "test_window_cod_orders": len(test),
    "gbm_rounds": gbm.best_iteration,
    "rows": rows,
}
Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
print({k: v for k, v in out.items() if k != "rows"})
