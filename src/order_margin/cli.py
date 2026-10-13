"""`order-margin`: run the full evaluation on data/ and write outputs/."""

from __future__ import annotations

import argparse
from pathlib import Path

from order_margin.pipeline import load, run, write


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, default=Path("outputs"))
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def log(msg: str) -> None:
        print(msg, flush=True)
        lines.append(msg)

    orders, truth = load(args.data)
    log(f"loaded {len(orders):,} orders from {args.data}")
    res = run(orders, truth, log=log)
    write(res, args.out)
    log("")
    log((args.out / "report.md").read_text())
    (args.out / "run_log.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
