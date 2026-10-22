"""Report cached predictions only: no training or additional test inference."""
import argparse
import json
import os
from pathlib import Path
import numpy as np
from generate_dataset import ROOT

METHODS=['training_mean','dsp','cnn','shuffled']


def table(scores):
    lines=['| Method | Cutoff MAE / RMSE (Hz) | Attack MAE / RMSE (ms) | Release MAE / RMSE (ms) | Normalized MSE |',
           '| --- | ---: | ---: | ---: | ---: |']
    for name in METHODS:
        metrics=scores[name]
        values=[' / '.join(format(metrics['parameters'][p][k],'.12g') for k in ['mae','rmse']) for p in ['cutoff','attack','release']]
        lines.append('| '+name+' | '+' | '.join(values)+f" | {metrics['normalized_mse']:.12g} |")
    return lines


def report(run):
    result=json.loads((run/'results.json').read_text())
    data=Path(result['run']['dataset_directory'])
    audit=json.loads((data/'data_audit.json').read_text())
    groups=result['test_groups']
    lines=['# Pitch and velocity robustness — measured offline results','',
           'One fixed CNN, one shuffled-training-label control, unchanged training configuration and DSP baseline. No tuning after test evaluation.','',
           'New synthetic dataset: 3,000 four-second, 48 kHz mono examples. Same restricted cutoff/attack/release ranges and saw waveform as the first experiment. Velocity arguments vary 0.4–1.0; actual MIDI bytes are saved. No recording-level amplitude normalization.','',
           'Training/validation pitches: 48, 50, 51, 52, 54, 55, 57, 59, 60. Held-out test pitches: 49, 53, 56, 58. These are unseen pitches within the training pitch span, not extrapolation.','',
           '## Aggregate test (300 examples)','']+table(result['test'])
    for name,group in groups.items():
        lines+=['',f"## {name} ({group['examples']} examples)",'']+table(group['methods'])
    lines+=['','## Interpretation','']
    for label,scores in [('Aggregate',result['test'])]+[(name,g['methods']) for name,g in groups.items()]:
        winner=min(['dsp','cnn'],key=lambda m:scores[m]['normalized_mse'])
        lines.append(f'- {label}: {winner} has lower overall normalized MSE.')
        for p in ['cutoff','attack','release']:
            best=min(['dsp','cnn'],key=lambda m:scores[m]['parameters'][p]['mae'])
            lines.append(f'  - {p}: {best} has lower MAE.')
    ratio=result['shuffled_label_sanity']['test_mse_ratio_shuffled_over_cnn']
    lines+=['',f'Shuffled-label / real-CNN aggregate test MSE ratio: **{ratio:.12g}×**. '+
            ('The expected degradation is observed.' if ratio>1 else 'The expected degradation is NOT observed; do not claim a successful leakage sanity check.'),
            'Only complete training target vectors were shuffled; validation/test targets remained correct. This sanity check does not prove every possible source of leakage is absent.','',
            'Pitch and velocity now confound the original DSP proxy. Its calibration remains three independent training-only interpolation tables; it has not been improved after inspecting the test set. A CNN advantage over this baseline does not establish superiority over all DSP methods.','',
            'Absolute scores should not be treated as a paired causal comparison to the first run: the dataset seed and test composition differ. No perceptual, arbitrary-recording, other-waveform or deployment generalization is established.','',
            '## Validation selection and training','',
            '| Condition | Selected epoch | Completed epochs | Best validation MSE | Training seconds |',
            '| --- | ---: | ---: | ---: | ---: |']
    for name in ['cnn','shuffled']:
        s=json.loads((run/name/'summary.json').read_text())
        lines.append(f"| {name} | {s['best_epoch']} | {s['epochs_completed']} | {s['best_validation_normalized_mse']:.12g} | {s['training_seconds']:.12g} |")
    lines+=['','The same 136,131-parameter CNN was trained once per label condition. Validation MSE alone selected checkpoints and early stopping. The test set was inferred exactly once per selected checkpoint; all subgroup metrics reuse the cached predictions.','',
            '## Actual offline forward latency','',
            '| Condition | Mean (ms) | Median (ms) | p95 (ms) | Minimum (ms) |',
            '| --- | ---: | ---: | ---: | ---: |']
    for name,t in result['offline_latency'].items():
        lines.append('| '+name+' | '+' | '.join(format(t[k],'.12g') for k in ['mean_ms','median_ms','p95_ms','minimum_ms'])+' |')
    lines+=['','CPU, four Torch threads, batch size one, 30 warmups and 200 timings. CNN forward only on a validation example, excluding WAV I/O, features and standardization. No real-time claim.','',
            '## Data and leakage checks','',
            f"- {audit['examples']} unique audio/target vectors; split counts {audit['split_counts']}; peak range {audit['peak_range']}.",
            f"- Performance isolation/readback audit: {audit['performance_audit']['status']}; {audit['performance_audit']['group_counts']}.",
            '- Smoke checks cover finite/unclipped audio, exact duration and parameter/MIDI readbacks, envelope visibility, spectral variation and log-mel distributions.',
            '- Inputs are waveform-derived log-mel tensors `[B,1,64,747]`. Targets are separate normalized tensors `[B,3]`. Pitch, velocity, group, names and manifest data never enter model.forward(x).',
            '- Train-only per-mel standardization independently recomputed; sampled train/validation feature caches exactly match WAV-derived recomputation.',
            '- Mutation regression tests verify label/manifest/filename changes leave inputs and model predictions unchanged.',
            '- Training-mean and DSP calibrations use training data only. No test data is opened during training.',
            '- Original first-experiment outputs and plugin runtime sources were preserved. No model or Python added to audio callback.','',
            '## Reproducibility and artifacts','',
            f"- Base Git commit: `{result['run']['provenance']['git_commit']}`; working-tree state and source hashes: `{run.relative_to(ROOT)}/run.json`.",
            f"- Dataset manifest SHA-256: `{result['run']['dataset_manifest_sha256']}`.",
            f"- Preprocessing SHA-256: `{result['run']['preprocessing_sha256']}`.",
            f"- PyTorch {result['run']['torch_version']}, Python {result['run']['python_version']}, CPU {result['run']['machine']}.",
            f'- Full float metrics: `{run.relative_to(ROOT)}/results.json`.',
            '- `test_predictions.csv` and `.npz` contain all ground truth and predictions. CSV physical units are Hz/seconds; envelope errors above are ms. `test_groups.json` maps example IDs to reporting groups.',
            '- Configuration/protocol: `pitch_velocity_config.json`, `training_config.json`, `PITCH_VELOCITY_PROTOCOL.md`.',
            '- Run log and test evidence: `build/ml-stage2-run.log`, `build/ml-stage2-tests.log`.',
            '', 'Stop point: experiment complete; no tuning, additional target or plugin integration followed the held-out results.']
    output=ROOT/'ml/PITCH_VELOCITY_RESULTS.md';output.write_text('\n'.join(lines)+'\n')
    os.environ.setdefault('MPLCONFIGDIR',str(run/'matplotlib-cache'))
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(13,4),layout='constrained')
    for ax,p in zip(axes,['cutoff','attack','release']):
        x=np.arange(len(METHODS))
        for offset,(group,entry) in zip([-.18,.18],groups.items()):
            ax.bar(x+offset,[entry['methods'][m]['parameters'][p]['mae'] for m in METHODS],.36,label=group)
        ax.set(xticks=x,xticklabels=['Mean','DSP','CNN','Shuffled'],yscale='log',title=p,ylabel='MAE (Hz)' if p=='cutoff' else 'MAE (ms)');ax.legend(fontsize=8)
    fig.savefig(run/'group_errors.png',dpi=140);plt.close(fig)
    print(f'Measured report: {output}',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,default=ROOT/'ml/runs/pitch_velocity')
    report(parser.parse_args().run.resolve())
