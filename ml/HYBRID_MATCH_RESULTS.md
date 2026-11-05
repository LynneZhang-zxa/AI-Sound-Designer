# Frozen-model hybrid matching validation

16 new independent SciPy references; no fitting, no reuse of old test predictions. Development validation, not a final generalization benchmark.

| Method | Mean distance ↓ | Median distance ↓ | Mean search seconds | Renders/reference |
|---|---:|---:|---:|---:|
| dsp | 1.82574686035 | 1.91442240962 | 0.669704817803 | 52 |
| hybrid | 1.8317095745 | 1.91442240962 | 0.653530497439 | 52 |

{"hybrid_wins": 1, "ties": 11, "hybrid_losses": 4, "mean_hybrid_minus_dsp": 0.005962714152456847}

Actual rendered candidates: 1664. Frozen checkpoint/preprocessing; unchanged plugin sources.

Offline forward timings (ms, cold first included; 16 examples): {'mean': 1.559338517836295, 'median': 0.6268334691412747}. Excludes feature extraction/search; no real-time claim.

The objective is log-mel RMSE + 2 envelope RMSE. Known pitch/gate are shared conditions; source nuisance labels never seed search. The hybrid uses CNN waveform/cutoff and the exact same DSP envelope seed as the baseline. Lower distance does not establish listening preference. Independent Butterworth fixtures do not establish arbitrary real-recording transfer.

Blind listening page: ml/runs/hybrid_match/index.html; mapping is separate in blind_key.json. No human preference numbers have been measured. All initializers, source settings and paired outcomes are retained. No plugin deployment or additional tuning followed this run.

Decision: this run does not justify deploying the hybrid. It wins once, ties eleven times and loses four times; average distance is slightly worse. The shared coarse grid explores all four waveforms and six cutoff values, so it often replaces either starting point with the same candidate. The CNN contributes only an extra initial candidate under this fixed search, which explains why improved parameter identification need not improve the final objective. This is an algorithmic limitation of this benchmark, not evidence that learned initialization can never help. No search redesign was performed after observing results.
