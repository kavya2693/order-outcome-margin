"""Inline exported JSON into a composition (renders cannot fetch files).

Replaces the block  /* NAME:BEGIN */ ... /* NAME:END */  with  const NAME = {...};  keeping only
the listed top-level keys, so the composition carries exactly the exported numbers.

Usage:
  python3 tools/inject_block.py assets/run.json compositions/s04-routes.html --block RUN \
      --keys daily,frontier,points
"""

import argparse
import json
import re

ap = argparse.ArgumentParser()
ap.add_argument("json")
ap.add_argument("html")
ap.add_argument("--block", required=True, help="marker name, e.g. SHEET")
ap.add_argument("--keys", required=True, help="comma-separated top-level keys to inline")
a = ap.parse_args()

with open(a.json) as fh:
    d = json.load(fh)
slim = {k: d[k] for k in a.keys.split(",")}
with open(a.html) as fh:
    html = fh.read()
b = a.block
block = f"/* {b}:BEGIN */ const {b} = " + json.dumps(slim, separators=(",", ":")) + f"; /* {b}:END */"
html, n = re.subn(rf"/\* {b}:BEGIN \*/.*?/\* {b}:END \*/", lambda _: block, html, flags=re.S)
assert n == 1, "marker not found"
with open(a.html, "w") as fh:
    fh.write(html)
print("injected", b, "with keys", list(slim))
