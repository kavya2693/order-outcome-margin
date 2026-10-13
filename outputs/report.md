# Run report

341,880 orders; test window 73,024 orders over 122 days,
35,389 of them cash on delivery. Booster stopped at 208 rounds
(class-weighted: 117). Realized test margin 3,059,183;
true expected margin 3,077,163, so the realized total sits
-0.83 standard deviations from what the true probabilities expect
(one SD of outcome noise is 0.70% of the total). Runtime 177.7s.

## Classification and calibration (test window)

| model | macro_f1 | log_loss | ece_mean | ece_fraud | prob_mae_vs_truth |
|---|---|---|---|---|---|
| class priors | 0.1767 | 0.7442 | 0.0063 | 0.0014 | 0.0533 |
| logistic, raw | 0.2894 | 0.6475 | 0.0028 | 0.0009 | 0.0260 |
| logistic + isotonic | 0.2969 | 0.6480 | 0.0028 | 0.0004 | 0.0262 |
| gbm, raw | 0.2927 | 0.6468 | 0.0025 | 0.0007 | 0.0258 |
| gbm + Platt | 0.2917 | 0.6468 | 0.0028 | 0.0005 | 0.0257 |
| gbm + isotonic | 0.2846 | 0.6478 | 0.0028 | 0.0006 | 0.0260 |
| gbm class-weighted, raw | 0.2729 | 1.3064 | 0.2066 | 0.0431 | 0.2078 |
| gbm class-weighted + isotonic | 0.2857 | 0.6571 | 0.0091 | 0.0009 | 0.0303 |
| true probabilities (ceiling) | 0.3441 | 0.6181 | 0.0021 | 0.0002 | 0.0000 |

## Predicted / observed outcome counts (1.000 is exact)

| model | count_ratio_returned | count_ratio_failed | count_ratio_fraud |
|---|---|---|---|
| class priors | 0.946 | 1.006 | 1.406 |
| logistic, raw | 0.993 | 1.000 | 1.204 |
| logistic + isotonic | 0.990 | 1.023 | 1.075 |
| gbm, raw | 0.988 | 1.010 | 1.132 |
| gbm + Platt | 0.984 | 1.012 | 1.090 |
| gbm + isotonic | 0.981 | 1.015 | 1.110 |
| gbm class-weighted, raw | 2.483 | 3.810 | 16.816 |
| gbm class-weighted + isotonic | 0.945 | 1.021 | 1.196 |
| true probabilities (ceiling) | 1.002 | 0.989 | 1.006 |

## Expected vs realized contribution margin (test window)

| model | margin_bias_pct | daily_mape | daily_mape_normal | daily_mape_peak |
|---|---|---|---|---|
| class priors | +1.72% | 10.65% | 9.59% | 22.54% |
| logistic, raw | -0.07% | 8.03% | 8.23% | 5.78% |
| logistic + isotonic | +0.42% | 8.02% | 8.24% | 5.52% |
| gbm, raw | +0.87% | 7.98% | 8.28% | 4.62% |
| gbm + Platt | +1.41% | 8.03% | 8.35% | 4.48% |
| gbm + isotonic | +1.17% | 7.94% | 8.26% | 4.42% |
| gbm class-weighted, raw | -183.47% | 183.09% | 180.16% | 215.86% |
| gbm class-weighted + isotonic | +4.28% | 9.27% | 8.67% | 15.99% |
| true probabilities (ceiling) | +0.59% | 8.03% | 8.25% | 5.53% |

## Margin error by outcome (expected minus noise-free realized, test window)

| outcome | logistic + isotonic | gbm + isotonic | true probabilities (ceiling) |
|---|---|---|---|
| delivered | +15,773 | +31,616 | +9,676 |
| returned | +4,385 | +15,078 | -720 |
| cancelled | -148 | -75 | +47 |
| failed_delivery | -3,820 | -2,401 | +1,450 |
| fraud_chargeback | -5,383 | -10,396 | +5,488 |
| total | +10,807 | +33,821 | +15,941 |

## COD blocking policy (test window, scored on true probabilities)

| policy | cod_orders_blocked | blocked_share_of_cod | orders_lost | margin_change | margin_change_pct | margin_per_order_lost |
|---|---|---|---|---|---|---|
| no blocking | 0 | 0.0% | 0 | +0 | +0.00% | nan |
| block every COD order | 35389 | 100.0% | 14,469 | -509,868 | -16.57% | -35.2 |
| rule of thumb: new customer and basket > 300 | 673 | 1.9% | 404 | -25,412 | -0.83% | -62.9 |
| risk score, same block rate as margin rule on calib (14.6%) | 5661 | 16.0% | 2,332 | -1,522 | -0.05% | -0.7 |
| margin rule, uncalibrated gbm | 5939 | 16.8% | 2,405 | +22,602 | +0.73% | +9.4 |
| margin rule, class-weighted gbm | 22788 | 64.4% | 9,233 | -171,784 | -5.58% | -18.6 |
| margin rule, gbm + isotonic | 5475 | 15.5% | 2,218 | +22,504 | +0.73% | +10.1 |
| margin rule, true probabilities (ceiling) | 5268 | 14.9% | 2,151 | +35,479 | +1.15% | +16.5 |
