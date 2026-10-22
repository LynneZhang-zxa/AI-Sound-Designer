# Offline hybrid estimator — validation results

Fixed policy: CNN cutoff; calibrated DSP attack and release. No retraining, new calibration, or test-set access.

| Method | Cutoff MAE / RMSE (Hz) | Attack MAE / RMSE (ms) | Release MAE / RMSE (ms) | Normalized MSE |
| --- | ---: | ---: | ---: | ---: |
| cnn | 61.6104984029 / 126.007810181 | 4.15207222415 / 7.16669322671 | 7.35996916269 / 11.8997825327 | 2.64352778866e-05 |
| dsp | 1052.62009406 / 1793.31034981 | 1.59694828947 / 2.04596677128 | 7.55162317874 / 13.843117145 | 0.00284449592986 |
| hybrid | 61.6105080137 / 126.007841235 | 1.59694828947 / 2.04596677128 | 7.55162317874 / 13.843117145 | 2.28551427043e-05 |
| training_mean | 1673.51294069 / 2543.07744386 | 91.3099813556 / 130.540480751 | 289.530053688 / 416.249711269 | 0.0181546748161 |

All 300 validation examples are included. These examples were already used for checkpoint selection; these are development results, not a fresh unbiased generalization estimate. The component choice was motivated by previously reported component performance. No new held-out test claim is made.

Full precision metrics and per-example predictions: `ml/runs/hybrid_validation/`. Existing test results and evaluation markers were left untouched.
