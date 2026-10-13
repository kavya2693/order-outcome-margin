"""Reliability diagram, daily margin and policy frontier figures."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from order_margin.calibration import reliability_curve  # noqa: E402
from order_margin.config import CLASSES  # noqa: E402

COLORS = ["#2a6fdb", "#d1495b", "#3c9d5d", "#8a5cc2", "#e08e0b"]


def plot_reliability(variants: dict[str, np.ndarray], y: np.ndarray, path: Path) -> None:
    fig, axes = plt.subplots(1, len(CLASSES), figsize=(18, 3.9))
    for k, (ax, cls) in enumerate(zip(axes, CLASSES, strict=True)):
        hit = (y == k).astype(float)
        hi = 0.0
        for (name, P), c in zip(variants.items(), COLORS, strict=False):
            x, obs = reliability_curve(P[:, k], hit)
            ax.plot(x, obs, "o-", ms=3, lw=1.2, color=c, label=name)
            hi = max(hi, float(x.max()), float(obs.max()))
        ax.plot([0, hi], [0, hi], "--", color="grey", lw=0.8)
        ax.set_title(cls.replace("_", " "))
        ax.set_xlabel("predicted probability")
        if k == 0:
            ax.set_ylabel("observed frequency")
    axes[0].legend(fontsize=7, loc="upper left")
    fig.suptitle("Reliability on the test window (15 equal-mass bins per class)")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_daily(daily: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 4))
    idx = pd.to_datetime(daily.index)
    ax.plot(idx, daily["realized"], color="black", lw=1.6, label="realized")
    for (name, c) in zip(
        ["gbm + isotonic", "gbm class-weighted, raw", "class priors"], COLORS[:3], strict=True
    ):
        ax.plot(idx, daily[name], color=c, lw=1.0, label=f"expected, {name}")
    ax.set_ylabel("contribution margin per day")
    ax.set_title("Expected vs realized daily margin, test window")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def plot_frontier(fr: pd.DataFrame, policy: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    for (name, g), c in zip(fr.groupby("ranking", sort=False), COLORS, strict=False):
        ax.plot(g["orders_lost"], g["margin_change"], lw=1.4, color=c, label=f"rank by {name}")
    pts = policy[~policy["policy"].isin(["no blocking"])]
    ax.scatter(pts["orders_lost"], pts["margin_change"], color="black", s=14, zorder=3)
    for _, r in pts.iterrows():
        ax.annotate(str(r["policy"]).split(",")[0][:28], (r["orders_lost"], r["margin_change"]), fontsize=7)
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_xscale("symlog", linthresh=100)
    ax.set_xlabel("orders lost (customers who do not switch to card)")
    ax.set_ylabel("change in expected contribution margin")
    ax.set_title("Blocking COD: margin gained against orders lost, test window")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
