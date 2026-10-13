"""Write the seeded order history to data/ (run with `make data`)."""

from __future__ import annotations

import argparse
from pathlib import Path

from order_margin.config import CLASSES, SEED
from order_margin.generate import write


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data"))
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    orders, _ = write(args.out, seed=args.seed)
    days = orders["order_ts"].dt.normalize().nunique()
    print(f"{len(orders):,} orders over {days} days, {orders['customer_id'].nunique():,} customers")
    share = orders["outcome"].value_counts(normalize=True).reindex(list(CLASSES))
    for name, s in share.items():
        print(f"  {name:<17} {s:7.2%}")
    print(f"  COD share         {(orders['payment'] == 'cod').mean():7.2%}")
    print(f"  realized margin   {orders['realized_margin'].sum():,.0f}")


if __name__ == "__main__":
    main()
