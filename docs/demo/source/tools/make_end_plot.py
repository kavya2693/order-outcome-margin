"""Draw the faint end-card graphic from the repo's COD frontier (outputs/policy_frontier.csv).

Curves only, no text, so nothing on the end card is unreadable. Same symlog x-axis as the repo plot.
Usage: python3 tools/make_end_plot.py <repo>/outputs assets/end-frontier.png
"""

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

src, dst = sys.argv[1].rstrip("/") + "/", sys.argv[2]
fr = pd.read_csv(src + "policy_frontier.csv")
style = {
    "margin gain, true probabilities": ("#c8d3de", (0, (4, 3)), 2.2),
    "risk score, gbm + isotonic": ("#ff8a73", "-", 2.6),
    "margin gain, gbm + isotonic": ("#3fd8a8", "-", 3.0),
}
fig, ax = plt.subplots(figsize=(5.2, 2.94), dpi=200)
for name, (c, ls, lw) in style.items():
    g = fr[fr["ranking"] == name]
    ax.plot(g["orders_lost"], g["margin_change"], color=c, ls=ls, lw=lw)
ax.axhline(0, color="#5d7086", lw=1.2)
ax.set_xscale("symlog", linthresh=100)
ax.set_xlim(0, 16000)
ax.set_ylim(-60000, 40000)
ax.axis("off")
fig.subplots_adjust(0, 0, 1, 1)
fig.savefig(dst, transparent=True)
print(dst)
