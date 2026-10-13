"""Seeded order history for a regional marketplace, two years of daily orders.

Writes `orders.csv` (what the business would see) and `truth/order_truth.csv` (the
outcome probabilities the orders were sampled from, under the actual payment method
and under card). Only the evaluation code reads the truth file.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from order_margin.config import CATEGORIES, CLASSES, DATA_END, DATA_START, REMOTE_ZONES, SEED, ZONES
from order_margin.economics import outcome_margins
from order_margin.world import true_proba

ZONE_P = np.array([0.27, 0.22, 0.16, 0.17, 0.10, 0.08])
CATEGORY_P = np.array([0.31, 0.15, 0.20, 0.18, 0.16])
VALUE_MEDIAN = {"fashion": 165.0, "electronics": 520.0, "home": 210.0, "beauty": 105.0, "grocery": 130.0}
ITEMS_LAMBDA = {"fashion": 1.0, "electronics": 0.25, "home": 0.8, "beauty": 1.3, "grocery": 4.5}
FRAUD_ACTIVE_DAYS = 45
OUTCOME_NOISE_SD = np.array([3.0, 5.0, 1.0, 3.0, 10.0])

# Calendar events. Ramadan dates follow the lunar calendar; the sale weeks are the
# regional November sale and the 11.11 day.
RAMADAN = [("2024-03-11", "2024-04-09"), ("2025-03-01", "2025-03-30")]
EID = ["2024-04-10", "2024-04-11", "2024-06-16", "2024-06-17", "2025-03-31", "2025-04-01", "2025-06-06"]
SALE_WEEKS = [("2024-11-22", "2024-11-30"), ("2025-11-21", "2025-11-29")]
SINGLES_DAY = ["2024-11-11", "2025-11-11"]


def _calendar(start: str, end: str) -> pd.DataFrame:
    days = pd.date_range(start, end, freq="D")
    cal = pd.DataFrame({"date": days})
    cal["is_ramadan"] = 0
    for a, b in RAMADAN:
        cal.loc[cal["date"].between(a, b), "is_ramadan"] = 1
    cal["is_peak"] = 0
    for a, b in SALE_WEEKS:
        cal.loc[cal["date"].between(a, b), "is_peak"] = 1
    cal.loc[cal["date"].isin(pd.to_datetime(SINGLES_DAY)), "is_peak"] = 1
    cal["is_eid"] = cal["date"].isin(pd.to_datetime(EID)).astype(int)
    return cal


def _daily_volume(cal: pd.DataFrame, base: float, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(len(cal)) / 365.0
    dow = cal["date"].dt.dayofweek.to_numpy()
    weekly = np.where(np.isin(dow, [3, 4, 5]), 1.12, 0.95)
    month = cal["date"].dt.month.to_numpy()
    summer = np.where(np.isin(month, [7, 8]), 0.84, 1.0)
    december = np.where(month == 12, 1.12, 1.0)
    lam = base * (1.0 + 0.22 * t) * weekly * summer * december
    lam *= np.where(cal["is_ramadan"] == 1, 1.15, 1.0)
    lam *= np.where(cal["is_peak"] == 1, 2.3, 1.0)
    lam *= np.where(cal["is_eid"] == 1, 0.7, 1.0)
    lam *= rng.lognormal(0.0, 0.08, len(cal))
    return rng.poisson(lam)


def _customers(n: int, start: pd.Timestamp, n_days: int, rng: np.random.Generator) -> pd.DataFrame:
    existing = rng.random(n) < 0.55
    # Existing base signed up over the prior three years; newcomers arrive over the window,
    # a little faster later on.
    offset = np.where(
        existing,
        -rng.integers(1, 3 * 365, n),
        (n_days * np.sqrt(rng.random(n))).astype(int),
    )
    fraudster = rng.random(n) < 0.006
    # Fraud accounts are opened shortly before they are used.
    offset = np.where(fraudster, rng.integers(0, n_days, n), offset)
    zone = rng.choice(len(ZONES), n, p=ZONE_P)
    cod_pref = np.clip(
        rng.beta(2.0, 2.2, n) + 0.15 * np.isin(np.array(ZONES)[zone], list(REMOTE_ZONES)), 0, 0.97
    )
    return pd.DataFrame(
        {
            "customer_id": np.arange(n),
            "signup": start + pd.to_timedelta(offset, unit="D"),
            "home_zone": np.array(ZONES)[zone],
            "activity": np.where(fraudster, 25.0, rng.lognormal(0.0, 1.1, n)),
            "cod_pref": np.where(fraudster, 0.05, cod_pref),
            "ret_trait": rng.normal(0.0, 0.7, n),
            "cancel_trait": rng.normal(0.0, 0.5, n),
            "refusal_trait": rng.normal(0.0, 0.75, n),
            "fraudster": fraudster.astype(int),
        }
    )


def _assign_customers(
    cust: pd.DataFrame, cal: pd.DataFrame, volume: np.ndarray, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(cust["signup"].to_numpy())
    signup_sorted = cust["signup"].to_numpy()[order]
    cw = np.cumsum(cust["activity"].to_numpy()[order])
    day_idx = np.repeat(np.arange(len(cal)), volume)
    ids = np.empty(len(day_idx), dtype=int)
    pos = 0
    for d, n in enumerate(volume):
        eligible = int(np.searchsorted(signup_sorted, cal["date"].iloc[d].to_datetime64(), side="right"))
        u = rng.random(n) * cw[eligible - 1]
        ids[pos : pos + n] = order[np.searchsorted(cw[:eligible], u, side="right")]
        pos += n

    # Fraud accounts burn out: after a few weeks they are closed or abandoned, so their
    # later draws go to an ordinary customer instead.
    fraud = cust["fraudster"].to_numpy()
    days = cal["date"].to_numpy()[day_idx]
    age = (days - cust["signup"].to_numpy()[ids]) / np.timedelta64(1, "D")
    stale = (fraud[ids] == 1) & (age > FRAUD_ACTIVE_DAYS)
    cw_clean = np.cumsum(np.where(fraud[order] == 1, 0.0, cust["activity"].to_numpy()[order]))
    eligible = np.searchsorted(signup_sorted, days[stale], side="right")
    u = rng.random(int(stale.sum())) * cw_clean[eligible - 1]
    ids[stale] = order[np.searchsorted(cw_clean, u, side="right")]
    return day_idx, ids


def generate(
    seed: int = SEED,
    start: str = DATA_START,
    end: str = DATA_END,
    base_daily: float = 360.0,
    n_customers: int = 120_000,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (orders, truth)."""
    rng = np.random.default_rng(seed)
    cal = _calendar(start, end)
    volume = _daily_volume(cal, base_daily, rng)
    cust = _customers(n_customers, cal["date"].iloc[0], len(cal), rng)
    day_idx, cid = _assign_customers(cust, cal, volume, rng)
    n = len(day_idx)
    c = cust.iloc[cid].reset_index(drop=True)
    d = cal.iloc[day_idx].reset_index(drop=True)
    fraudster = c["fraudster"].to_numpy()

    # Evening peak, pushed later in the night during Ramadan.
    hour = np.clip(np.round(rng.normal(20.0, 3.5, n) + 2.5 * d["is_ramadan"].to_numpy()), 0, 23) % 24
    minute = rng.integers(0, 60, n)
    ts = d["date"] + pd.to_timedelta(hour, unit="h") + pd.to_timedelta(minute, unit="m")

    cat_p = np.where(fraudster[:, None] == 1, np.array([0.1, 0.65, 0.15, 0.05, 0.05]), CATEGORY_P)
    cat_idx = (rng.random(n)[:, None] > np.cumsum(cat_p, axis=1)).sum(axis=1)
    category = np.array(CATEGORIES)[np.clip(cat_idx, 0, len(CATEGORIES) - 1)]
    lam = pd.Series(category).map(ITEMS_LAMBDA).to_numpy(float)
    n_items = 1 + rng.poisson(lam)
    median = pd.Series(category).map(VALUE_MEDIAN).to_numpy(float)
    value = median * n_items**0.55 * rng.lognormal(0.0, 0.55, n)
    bulk = rng.random(n) < 0.003
    value = np.where(bulk, value * rng.uniform(5, 12, n), value)
    value = np.round(np.where(fraudster == 1, value * 1.8, value), 2)

    peak = d["is_peak"].to_numpy()
    discount = np.round(np.clip(rng.beta(1.2, 12.0, n) + 0.22 * peak * rng.random(n), 0, 0.7), 3)
    coupon = (rng.random(n) < 0.12 + 0.3 * peak).astype(int)

    zone = np.where(rng.random(n) < 0.9, c["home_zone"].to_numpy(), np.array(ZONES)[rng.choice(6, n, p=ZONE_P)])
    remote = np.isin(zone, list(REMOTE_ZONES))
    promised = 1 + remote * rng.integers(2, 4, n) + (rng.random(n) < 0.35) + peak

    account_age = (d["date"] - c["signup"]).dt.days.to_numpy()
    new = account_age < 30
    p_cod = np.clip(c["cod_pref"].to_numpy() + 0.15 * new - 0.15 * (category == "electronics"), 0.02, 0.97)
    u = rng.random(n)
    payment = np.where(u < p_cod, "cod", np.where(rng.random(n) < 0.7, "card", "wallet"))

    addr = np.clip(rng.beta(6.0, 2.0, n) - 0.18 * remote, 0.0, 1.0)
    device_new = (rng.random(n) < np.where(fraudster == 1, 0.75, 0.08)).astype(int)
    phone_verified = (rng.random(n) > np.where(fraudster == 1, 0.55, 0.06)).astype(int)

    world = pd.DataFrame(
        {
            "payment": payment,
            "category": category,
            "zone": zone,
            "basket_value": value,
            "n_items": n_items,
            "discount_pct": discount,
            "promised_days": promised,
            "account_age_days": account_age,
            "is_peak": peak,
            "is_ramadan": d["is_ramadan"].to_numpy(),
            "addr_quality_true": addr,
            "device_new_true": device_new,
            "phone_verified": phone_verified,
            "ret_trait": c["ret_trait"].to_numpy(),
            "cancel_trait": c["cancel_trait"].to_numpy(),
            "refusal_trait": c["refusal_trait"].to_numpy(),
            "fraudster": fraudster,
        }
    )
    p_true = true_proba(world)
    p_card = true_proba(world, np.full(n, "card"))
    outcome = (rng.random(n)[:, None] > np.cumsum(p_true, axis=1)).sum(axis=1)
    outcome = np.clip(outcome, 0, len(CLASSES) - 1)

    margins = outcome_margins(world)
    realized = margins[np.arange(n), outcome] + rng.normal(0.0, OUTCOME_NOISE_SD[outcome])

    # What the order system records: geocoding fails on some addresses (more often on
    # the poor ones), and the device fingerprint is missing when app tracking is off.
    addr_obs = np.where(rng.random(n) < 0.04 + 0.12 * (addr < 0.4), np.nan, np.round(addr, 3))
    device_obs = np.where(rng.random(n) < 0.06, np.nan, device_new)

    orders = pd.DataFrame(
        {
            "order_id": np.arange(n),
            "customer_id": cid,
            "order_ts": ts,
            "category": category,
            "n_items": n_items,
            "basket_value": value,
            "discount_pct": discount,
            "coupon_used": coupon,
            "payment": payment,
            "zone": zone,
            "promised_days": promised,
            "account_age_days": account_age,
            "address_quality": addr_obs,
            "device_new": device_obs,
            "phone_verified": phone_verified,
            "is_peak": peak,
            "is_ramadan": d["is_ramadan"].to_numpy(),
            "outcome": np.array(CLASSES)[outcome],
            "realized_margin": np.round(realized, 2),
        }
    ).sort_values("order_ts", kind="stable")
    truth = pd.DataFrame({"order_id": np.arange(n)})
    for k, name in enumerate(CLASSES):
        truth[f"p_{name}"] = p_true[:, k]
    for k, name in enumerate(CLASSES):
        truth[f"p_card_{name}"] = p_card[:, k]
    truth["fraudster"] = fraudster
    return orders.reset_index(drop=True), truth


def write(out_dir: Path, **kwargs: object) -> tuple[pd.DataFrame, pd.DataFrame]:
    orders, truth = generate(**kwargs)  # type: ignore[arg-type]
    (out_dir / "truth").mkdir(parents=True, exist_ok=True)
    orders.to_csv(out_dir / "orders.csv.gz", index=False)
    truth.to_csv(out_dir / "truth" / "order_truth.csv.gz", index=False, float_format="%.6g")
    return orders, truth
