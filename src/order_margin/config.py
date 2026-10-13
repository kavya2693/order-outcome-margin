"""Shared constants: outcome classes, unit economics and the time split.

Every number the margin calculation depends on lives here, so a finance reviewer can
check one file rather than reading the model code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CLASSES: tuple[str, ...] = ("delivered", "returned", "cancelled", "failed_delivery", "fraud_chargeback")
N_CLASSES = len(CLASSES)
DELIVERED, RETURNED, CANCELLED, FAILED, FRAUD = range(N_CLASSES)

CATEGORIES: tuple[str, ...] = ("fashion", "electronics", "home", "beauty", "grocery")
PAYMENTS: tuple[str, ...] = ("cod", "card", "wallet")
ZONES: tuple[str, ...] = ("metro_a", "metro_b", "metro_c", "suburb", "remote_north", "remote_south")
REMOTE_ZONES: frozenset[str] = frozenset({"remote_north", "remote_south"})


@dataclass(frozen=True)
class Economics:
    """Per-order unit economics in local currency. Values are net of discount and VAT."""

    gross_margin: dict[str, float] = field(
        default_factory=lambda: {
            "fashion": 0.42,
            "electronics": 0.13,
            "home": 0.31,
            "beauty": 0.36,
            "grocery": 0.19,
        }
    )
    # Share of cost of goods that cannot be recovered when an item comes back:
    # opened beauty and grocery are written off, fashion mostly goes back on the shelf.
    resale_loss: dict[str, float] = field(
        default_factory=lambda: {
            "fashion": 0.12,
            "electronics": 0.18,
            "home": 0.15,
            "beauty": 0.65,
            "grocery": 1.0,
        }
    )
    ship_out_base: float = 12.0
    ship_out_remote: float = 7.0
    ship_out_per_sqrt_item: float = 1.5
    return_ship: float = 11.0
    return_handling: float = 6.0
    rto_share: float = 0.8  # return-to-origin leg as a share of the outbound leg
    failed_handling: float = 4.0
    cancel_cost: float = 2.5
    free_shipping_threshold: float = 100.0
    shipping_fee: float = 9.0
    cod_fee_flat: float = 4.0
    cod_fee_rate: float = 0.010
    card_fee_flat: float = 1.0
    card_fee_rate: float = 0.022
    wallet_fee_rate: float = 0.015
    chargeback_fee: float = 45.0


ECON = Economics()

# Time split. The early-stopping window sits inside the training period so the
# calibration window is never seen by the booster.
TRAIN_END = "2025-02-28"
EARLY_STOP_END = "2025-04-30"
CALIB_END = "2025-08-31"
DATA_START = "2024-01-01"
DATA_END = "2025-12-31"

# Share of customers blocked from cash on delivery who complete the order with a card.
# In production this comes from a holdout test of the checkout prompt; here it is an input.
COD_TO_CARD_CONVERSION = {"new": 0.40, "returning": 0.60}
NEW_CUSTOMER_DAYS = 30

SEED = 20260913
