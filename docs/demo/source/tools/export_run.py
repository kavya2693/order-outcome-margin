"""Export the data behind slide 06 ("The system running") from the repo's own outputs.

Reads outputs/daily_margin.csv, outputs/policy_frontier.csv and outputs/policy.csv (written by
`make run`) and writes assets/run.json. The composition draws the charts from these numbers as
SVG, so no value is retyped or redrawn by hand.

Usage: python3 tools/export_run.py <repo>/outputs assets/run.json
       python3 tools/inject_sheet.py assets/run.json compositions/s04-routes.html --block RUN \
           --keys daily,frontier,points
"""

import json
import sys
from pathlib import Path

import pandas as pd

src, dst = Path(sys.argv[1]), Path(sys.argv[2])

daily = pd.read_csv(src / "daily_margin.csv")
cols = ["realized", "class priors", "gbm + isotonic", "gbm class-weighted, raw"]
rows = [[int(r["peak"])] + [round(float(r[c])) for c in cols] for _, r in daily.iterrows()]

fr = pd.read_csv(src / "policy_frontier.csv")
frontier = {
    name: [
        [round(float(a), 1), round(float(b))]
        for a, b in zip(g["orders_lost"], g["margin_change"], strict=True)
    ]
    for name, g in fr.groupby("ranking", sort=False)
}

pol = pd.read_csv(src / "policy.csv").set_index("policy")
pick = {
    "margin_rule": "margin rule, gbm + isotonic",
    "rule_of_thumb": "rule of thumb: new customer and basket > 300",
    "block_all": "block every COD order",
}


def point(policy: str) -> list[float]:
    return [round(float(pol.loc[policy, "orders_lost"]), 1), round(float(pol.loc[policy, "margin_change"]))]


points = {k: point(v) for k, v in pick.items()}
points["risk_score"] = point(next(p for p in pol.index if p.startswith("risk score")))

out = {
    "daily_columns": ["peak", *cols],
    "daily": rows,
    "frontier": frontier,
    "points": points,
}
dst.write_text(json.dumps(out, separators=(",", ":")))
print(dst, len(rows), "days", {k: len(v) for k, v in frontier.items()}, points)
