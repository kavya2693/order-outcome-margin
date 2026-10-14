"""Inline the exported COD decision sheet into compositions/value.html (renders cannot fetch files).

Usage: python3 tools/inject_sheet.py assets/cod_sheet.json compositions/value.html \
         --rows 315400,316055,316096,316229,315744,316309 --animate 315400,316096,316229,315744
"""

import argparse
import json
import re

ap = argparse.ArgumentParser()
ap.add_argument("sheet")
ap.add_argument("html")
ap.add_argument("--rows", required=True, help="order ids shown as sheet rows, in order")
ap.add_argument("--animate", required=True, help="order ids shown as checkouts in the 2D scene (max 4)")
a = ap.parse_args()

with open(a.sheet) as fh:
    d = json.load(fh)
by_id = {r["order_id"]: r for r in d["rows"]}
rows = [int(v) for v in a.rows.split(",")]
anim = [int(v) for v in a.animate.split(",")]
keys = ("order_id", "zone", "category", "basket", "p_refuse", "conv", "em_cod", "em_card", "gain", "block")
slim = {
    k: d[k]
    for k in ("day", "orders", "cod_orders", "blocked", "kept", "expected_orders_lost", "day_true_gain")
} | {"rows": [{k: by_id[v][k] for k in keys} | {"animate": anim.index(v) if v in anim else -1} for v in rows]}
with open(a.html) as fh:
    html = fh.read()
block = "/* SHEET:BEGIN */ const SHEET = " + json.dumps(slim, separators=(",", ":")) + "; /* SHEET:END */"
html, n = re.subn(r"/\* SHEET:BEGIN \*/.*?/\* SHEET:END \*/", lambda _: block, html, flags=re.S)
assert n == 1, "marker not found"
with open(a.html, "w") as fh:
    fh.write(html)
print("injected", len(slim["rows"]), "rows,", len(anim), "animated")
