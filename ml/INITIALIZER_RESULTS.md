# Expanded-domain initializer — measured results

One frozen experiment, no tuning or deployment. Model predicts three normalized targets plus waveform; nuisance parameters vary.

## Test prediction metrics (300 examples)

| Method | Cutoff MAE / RMSE Hz | Attack MAE / RMSE ms | Release MAE / RMSE ms | Norm MSE | Wave accuracy | Macro F1 |
|---|---:|---:|---:|---:|---:|---:|
| model | 688.705366325 / 1293.39340982 | 36.3590156908 / 56.9098590389 | 42.447037703 / 65.3794807688 | 0.00294681009452 | 0.933333333333 | 0.932626056192 |
| shuffled | 1714.19107152 / 2552.06418939 | 101.20155933 / 135.665164928 | 247.166692608 / 365.667856948 | 0.0173305526526 | 0.36 | 0.285790672501 |
| training_mean | 1708.94157319 / 2511.48343037 | 98.0511811995 / 138.632206936 | 251.668558978 / 375.191409942 | 0.0172954981822 | 0.25 | 0.1 |
| dsp | 1524.75296034 / 2335.58182999 | 1.93528373479 / 2.43435220944 | 4.18759620241 / 7.94860226747 | 0.00816406117348 | 0.25 | 0.1 |

## Equal-budget search: held_out_synth

| Method | Mean score | Median score | Mean seconds | Renders |
|---|---:|---:|---:|---:|
| default | 2.38498271242 | 1.8819579904 | 0.682497050686 | 52 |
| dsp | 0.753720886595 | 0.642169044812 | 0.680607824219 | 52 |
| model | 1.18093659315 | 0.967475090803 | 0.676077065225 | 52 |

Model vs default: wins 24, ties 0, losses 8; mean difference (model minus baseline) -1.20404611927.

Model vs dsp: wins 7, ties 0, losses 25; mean difference (model minus baseline) 0.427215706557.

## Equal-budget search: independent_scipy

| Method | Mean score | Median score | Mean seconds | Renders |
|---|---:|---:|---:|---:|
| default | 2.49045822366 | 2.40233347721 | 0.631762260251 | 52 |
| dsp | 1.61887938127 | 1.53245756836 | 0.63192261965 | 52 |
| model | 1.73995304276 | 1.52255270216 | 0.6314435104 | 52 |

Model vs default: wins 6, ties 0, losses 2; mean difference (model minus baseline) -0.750505180898.

Model vs dsp: wins 2, ties 0, losses 6; mean difference (model minus baseline) 0.121073661488.

## Sanity, timing and interpretation

Shuffled/real test normalized-MSE ratio: 5.88112300987×.
Validation-example CPU forward timing: {'mean': 0.5869495650000001, 'median': 0.577625, 'p95': 0.7362306, 'scope': 'CPU4 threads batch1; 30 warmups/200 repetitions; validation example; forward only'}. No real-time claim.

Parameter errors and waveform confusion matrix/seen-unseen groups are retained in full precision in results.json. Sine/filter and nuisance/envelope ambiguities mean low numerical error alone cannot establish sound similarity.

The practical comparison uses the same 52 renders, objective and fixed nuisance defaults for all methods. Pitch and gate are shared known task conditions; no true nuisance settings seed the renderer. No claim of fewer renders is made from this fixed-budget test. Negative comparisons are retained.

The search evaluates 32 balanced held-out synth references and eight independent SciPy fixtures, not real third-party synth recordings. No listening test or arbitrary-audio generalization is established. No additional fine-tuning, tuning, or plugin integration followed these results.

Artifacts: `ml/runs/initializer_experiment`. Per-example parameter predictions: test_predictions.csv/.npz. All search outcomes: search_results.json. Protocol/config: INITIALIZER_PROTOCOL.md and initializer_config.json. Source, renderer, commit, environment and preprocessing identities are recorded in the run/dataset manifests.


## Decision from this run

The CNN improves cutoff prediction and identifies waveform, but the DSP baseline predicts attack/release much more accurately. Under the identical 52-render budget, CNN initialization loses to DSP initialization on 25/32 held-out synth references and 6/8 independent fixtures. The lower aggregate normalized parameter MSE therefore did not translate into better matching than the DSP baseline. Do not deploy this checkpoint as a replacement for the existing matching mechanism. This run is complete; no post-test model tuning or extra fit was performed.

The shuffled control is near the training-mean normalized-MSE baseline, 5.88112300987 times worse than the real model. This is consistent with learning a useful audio relationship; it is a sanity check, not a proof of absence of every form of leakage. Waveform-only input mutation checks and train-only preprocessing checks also passed.

Training: main model 35 epochs, selected epoch 34, 146.698383 seconds; shuffled control 20 epochs, selected epoch 13, 83.4215144169 seconds. Both start with the same initialization and batch-order seed. Each checkpoint sees the final test features once. Final artifact audit confirms 6,240 actual rendered candidates and unchanged plugin sources; 29 Python tests and both C++ tests passed. Detailed evidence is in `ml/runs/initializer_experiment/completion_audit.json`.
