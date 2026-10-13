# order-outcome-margin

[![ci](https://github.com/kavya2693/order-outcome-margin/actions/workflows/ci.yml/badge.svg)](https://github.com/kavya2693/order-outcome-margin/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.11-blue)
![license](https://img.shields.io/badge/license-MIT-green)

Which orders will lose money, how much the day will really earn, and when cash on delivery
should be switched off: a five-outcome order model priced with unit economics.

## The problem

A regional marketplace ships around 470 orders a day, and roughly half of them are paid in
cash at the door. Most orders arrive and earn a margin. The rest lose money in four different
ways: the customer returns the item, cancels before dispatch, refuses the parcel at the door
(the courier carries it out and back again and no cash is collected), or, on a card, disputes
the charge as fraud. A refused parcel to a remote zone, a returned lipstick that has to be
written off, and a laptop bought with a stolen card cost very different amounts.

Two teams live with this. Finance closes each day with an expected contribution margin built
from last quarter's average return and failure rates, and then explains the gap to the ledger
when a sale week or a fraud wave hits. Operations decides when to hide the COD option at
checkout, usually with a rule like "new customer and a big basket", without knowing whether the
orders it pushes away were worth more than the parcels it stops being refused.

## Why it is hard

Accuracy is not the problem. The outcomes are imbalanced (79% delivered, 0.3% fraud), so a model
that predicts "delivered" for everything is right four times out of five and useless. What the
business needs is a probability for each outcome that can be multiplied by money, which means
the probabilities have to be calibrated, and the rarest outcome is the most expensive one.

The COD decision is harder again. Blocking COD does not simply drop an order: some customers pay
by card instead, and a card order is a different order, with fewer refusals but a chance of a
chargeback. Judging a block rule needs a counterfactual nobody observes.

## The approach

A LightGBM multiclass model predicts all five outcomes at once, so the probabilities sum to one.
They are calibrated (isotonic and Platt, one class against the rest) on a four-month window the
booster never saw. The money is kept out of the model: `economics.py` prices every order under
every outcome (gross margin, both shipping legs, payment fees, resale loss on returns, chargeback
fee), and expected margin is the probability-weighted sum.

The key decision is to block COD on **expected gain**, not on risk:

```
block if  conversion x E[margin | paid by card]  -  E[margin | COD]  >  0
```

where the card case is the same order scored again with the payment feature switched, and
conversion is the share of blocked customers who switch to a card (40% for accounts younger than
30 days, 60% otherwise, an input that would come from a checkout test). The usual alternative, a
risk score of P(failed) + P(cancelled), is kept as the comparison at the same block rate.

## The result

Test window: September to December 2025, 73,024 orders over 122 days, including the November
sale week. All numbers below are from `outputs/report.md`.

| Model | log-loss | macro-F1 | mean classwise ECE | total margin vs realized | daily margin error, sale days |
|---|---|---|---|---|---|
| Class priors (finance's flat rates) | 0.7442 | 0.177 | 0.0063 | +1.72% | 22.5% |
| Logistic regression + isotonic | 0.6479 | 0.297 | 0.0028 | +0.51% | 5.5% |
| LightGBM, raw | **0.6469** | 0.294 | 0.0027 | +0.71% | 4.6% |
| LightGBM + isotonic | 0.6478 | 0.286 | 0.0035 | +1.06% | **4.3%** |
| LightGBM, class-weighted, raw | 1.3050 | 0.272 | 0.2063 | **-182.8%** | 215.0% |
| LightGBM, class-weighted + isotonic | 0.6572 | 0.288 | 0.0093 | +4.24% | 16.0% |
| True probabilities (ceiling) | 0.6181 | 0.344 | 0.0021 | +0.59% | 5.5% |

| COD policy on the test window (35,389 COD orders) | Orders lost | Margin change |
|---|---|---|
| Block every COD order | 14,469 | -509,868 (-16.6%) |
| Rule of thumb: new customer and basket over 300 | 404 | -25,412 |
| Risk score, same block rate as the margin rule | 2,360 | -2,113 |
| **Margin rule, LightGBM + isotonic** | 2,228 | **+22,258 (+0.72%)** |
| Margin rule, true probabilities (ceiling) | 2,151 | +35,479 (+1.15%) |

What the numbers say, including the parts that disappoint:

- **The margin rule makes money where the risk rule does not.** At the same block rate the margin
  rule is 24,371 better than ranking on risk (order bootstrap 95% CI 21,580 to 27,556). The risk
  rule blocks risky orders that are still worth more as COD than as a card order that may never
  happen; the margin rule asks whether the card version of the order is worth more. It recovers
  63% of the gain available to a model that knew the true probabilities.
- **Gradient boosting barely beats logistic regression.** Log-loss 0.6469 against 0.6475 raw, and
  logistic regression is closer on the total margin. The outcome process here is close to
  additive on the log-odds scale, which is the shape a logistic model assumes, so there is little
  for trees to find. I would not claim a boosting advantage from this data.
- **Calibration did nothing for the plain booster.** Multiclass log-loss is a proper scoring rule,
  so the raw LightGBM was already calibrated (ECE 0.0027); isotonic made log-loss slightly worse.
  Calibration earned its place only after class weighting, which is the usual fix for a low
  macro-F1: weighting pushed predicted fraud to 16 times the observed count, turned the daily
  margin forecast negative (-183%), and still did not raise macro-F1 (0.272 against 0.294).
  Isotonic brought ECE from 0.206 to 0.009, but the margin was still 4.2% off. **Macro-F1 and
  margin accuracy disagree**: logistic + isotonic has the best macro-F1 of the trained models and
  is not the best on the margin of sale days.
- **Daily margin error cannot separate the models on ordinary days.** Every model, including the
  true probabilities, is about 8% off per day, because one or two fraud chargebacks a day move
  the total by that much. The gap between models only shows on sale days (22.5% for
  flat rates, 4.3% for the booster) and in the four-month total.
- **The gain depends on the conversion assumption.** With the decisions fixed, if real card
  conversion is 20 points below the assumed rate the rule breaks even, and at 30 points below it
  loses 9,714. This is the experiment that could embarrass the result, and it is the reason the
  conversion rate has to be measured before this rule goes live.

![policy frontier](outputs/policy_frontier.png)

## How it works

```
orders.csv ──► features.py ──► models.py ──────► calibration.py ──► economics.py ──► pipeline.py
  (2 years)    order fields    class priors       isotonic / Platt    margin under     daily expected
               + lagged        logistic           fitted on May-Aug   each of the 5    vs realized;
               customer        LightGBM (raw,     2025, renormalised  outcomes         COD policy
               history         class-weighted)                                         scored on truth
```

- **Time split.** Train January 2024 to February 2025; early stopping March to April 2025;
  calibration May to August 2025; test September to December 2025. Hyperparameters were chosen
  from four settings on the early-stopping and calibration windows, never on the test window.
- **Leakage guard.** A return or refusal is only known days later, so customer history rates use
  orders placed at least 14 days earlier, shrunk towards fixed long-run rates. A test that flips
  an unresolved outcome and checks that no feature moves caught a real leak during the build: the
  shrinkage target had been computed from the whole file, test window included.
- **Counterfactual.** For each COD order the model is scored twice, as COD and as card, both
  through the same calibrator. The policy is then scored with the generator's true probabilities
  under both payment methods, never with the model that made the decision.
- **Stop conditions.** Early stopping on the March to April window (100 rounds patience); the
  plain booster stopped at 186 rounds.

## Running it

```bash
git clone https://github.com/kavya2693/order-outcome-margin
cd order-outcome-margin
uv sync
make run      # generate the order history, fit, calibrate, score; about 2 minutes on a laptop
make check    # ruff, ruff format, mypy, pytest
```

Outputs land in `outputs/`: `report.md` (every table above), `metrics.csv`, `policy.csv`,
`conversion_sensitivity.csv`, `margin_error_by_outcome.csv`, `daily_margin.csv`, and the three
figures. With Docker: `docker build -t order-outcome-margin . && docker run --rm order-outcome-margin`.

## The data

The dataset is generated by the seeded script `scripts/generate_data.py` (`make data`) and sized
to the production problem; the production data is proprietary. It covers a marketplace in six
delivery zones (two of them remote) over 2024 and 2025: 341,880 orders from about 78,000
customers, five product categories, COD around 48% of orders.

Daily volume has growth, a weekly cycle, a summer dip, a Ramadan lift with late-night ordering,
Eid dips, a December lift, and a November sale week at 2.3 times normal volume with deeper
discounts and longer delivery promises. Outcomes are drawn from a multinomial logit that depends
on order fields and on hidden customer traits (a tendency to return, to cancel, to refuse at the
door) that the model can only infer from history. About 0.6% of accounts are fraud accounts that
buy electronics on new devices and burn out within 45 days. Fraud chargebacks need a card, so COD
orders cannot end that way. Basket values are log-normal with 0.3% bulk orders at 5 to 12 times
normal size; addresses that fail to geocode (more often poor ones) and device fingerprints are
missing for 4 to 16% and 6% of orders. Realized margin adds outcome-specific noise to the unit
economics. The true probabilities, under the actual payment and under card, are written to
`data/truth/` and read only by the evaluation code.

The limit that matters: the generator's outcome process is additive in log-odds with a few
interactions, which favours logistic regression and leaves the booster little to find. Real
order data is likely to be less kind to a linear model.

## Tests

24 tests, run in CI without any network access or model server. The two that matter most:

- `test_features.py::test_unresolved_outcome_cannot_change_features` changes the outcome of an
  order placed five days earlier and requires every history feature to stay the same. It failed
  on the first build and found the shrinkage-target leak described above.
- `test_calibration.py` checks the verifier before trusting it: classwise ECE is near zero on
  predictions sampled from their own probabilities, at least four times larger on a
  deliberately overconfident version, and both calibrators repair that overconfident model on
  fresh data.

The pipeline tests run the whole evaluation on a small history and require that the true
probabilities beat every model on log-loss, that class weighting breaks the margin forecast and
isotonic repairs it, and that the margin rule beats blocking every COD order.

## Known limitations

- **Biggest gap: the COD counterfactual is assumed, not measured.** The card version of an order
  comes from switching one feature, and the conversion rate is an input. In this data, COD choice
  is not confounded with the hidden traits; in real data it will be (customers who choose COD
  differ in ways the model does not see), and the sensitivity table shows the gain disappears if
  conversion is 20 points lower than assumed. A randomised holdout on the checkout prompt is the
  fix.
- Orders lost are counted, not priced. A customer pushed away may not come back; the lifetime
  value of that customer is not in the margin change.
- Outcomes are settled at a fixed 14-day lag. Real returns windows are longer for some categories
  and chargebacks can arrive months later, which would make the history features staler.
- One seed and one test window. The bootstrap interval covers which orders arrived, not a
  different year or a different fraud pattern.
- Unit economics are a single table per category. Real courier rates vary by weight and contract.

## Insights and learning

I picked this problem because the gap between a classifier and a business number is where most
outcome models stop being useful. A model with a good macro-F1 can still be useless to finance,
and this project shows it directly: the class-weighted booster had a respectable F1 and forecast
a negative daily margin for a business that earns about 25,000 a day.

The surprise was how little calibration did for the model that was trained the plain way. I
expected isotonic to be the step that made the margin forecast work; instead the unweighted
booster was already calibrated, and isotonic only mattered as the repair for a choice (class
weighting) that should not have been made. The second surprise was the risk rule. Ranking COD
orders by refusal risk is what I would have built first, and at the same block rate it lost money,
because the riskiest orders are often the most profitable ones when they do arrive.

What I got wrong at first: the fraud accounts in the generator stayed active forever, so the fraud
rate crept up over two years and every model looked badly calibrated on fraud in the test window.
That was an artefact of the data, not a finding, and I fixed the generator rather than report it.
The leakage test also caught my own mistake in the history features.

Next I would replace the assumed conversion rate with an uplift estimate from a randomised
checkout test, price the lost customers with a simple lifetime value, and add a second test window
with a fraud pattern the training data never saw, to see whether the calibration holds when the
rarest class changes shape.

## License

MIT
