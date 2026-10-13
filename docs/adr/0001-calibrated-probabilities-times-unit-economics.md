# ADR-0001: Score orders in money from calibrated multiclass probabilities; decide COD on expected gain, not risk

## Status
Accepted

## Context
A marketplace that offers cash on delivery loses money on an order in four different ways:
the customer returns it, cancels it, refuses it at the door, or (on a card) disputes it as
fraud. Each of these costs a different amount, and the amount depends on the order: a refused
parcel to a remote zone costs two long shipping legs, a returned lipstick is written off, a
fraudulent laptop costs its full cost of goods plus a chargeback fee. Finance wants a daily
expected contribution margin it can reconcile against the ledger, and operations wants a rule
for when to switch COD off at checkout.

## Decision
- One multiclass model over five outcomes (delivered, returned, cancelled, failed delivery,
  fraud chargeback), not four separate binary models. The outcomes are mutually exclusive, and
  a softmax keeps the five probabilities summing to one, which a set of binary models does not.
- The money lives outside the model. `economics.py` builds a margin for every order under every
  outcome; expected margin is the dot product with the probabilities. Finance can change a fee
  without retraining anything.
- The probabilities must be calibrated, because they are multiplied by money. Calibration is
  checked with classwise ECE on equal-mass bins and with predicted/observed counts per class, on
  a window the booster never saw. Isotonic and Platt are both fitted one-vs-rest and the rows
  renormalised.
- No class weighting. It is the usual response to a low macro-F1 on rare classes, and it shifts
  every probability away from the truth, which the margin calculation cannot absorb.
- COD is blocked when `conversion x E[margin | card] - E[margin | COD] > 0`, where the card
  scenario is the same order scored again with the payment feature switched. The risk rule
  teams usually run (rank on P(failed) + P(cancelled)) is kept as the comparison at equal volume.
- Time split: train Jan 2024 to Feb 2025, early stopping Mar to Apr 2025, calibration May to Aug
  2025, test Sep to Dec 2025 (including the November sale week). Hyperparameters were chosen from
  four settings on the early-stopping and calibration windows only.
- Policies are scored on the generator's true outcome probabilities under both payment methods,
  never on the model that made the decision.

## Alternatives rejected
- **Separate binary models per outcome.** Easier to own per team, but the probabilities do not
  add up, and an order can end up 30% likely to be returned and 90% likely to be delivered.
- **Predict margin directly with a regressor.** Gives one number per order and no way to price a
  fee change or a COD switch without retraining, and hides which outcome drives a bad forecast.
- **Temperature scaling.** A single parameter cannot fix class-specific miscalibration, which is
  exactly what class weighting produces.
- **Causal uplift model for the COD switch.** The right tool once a randomised holdout of the
  checkout prompt exists. Without one, the payment-switch counterfactual and an assumed
  conversion rate are stated as assumptions and stress-tested instead.

## Consequences
- The policy's value depends on the card-conversion assumption; the run reports how the gain
  changes when real conversion is 10 to 30 points lower than assumed.
- The payment-switch counterfactual is only as good as the model's payment coefficients; on real
  data, COD choice is confounded with things the model cannot see.
