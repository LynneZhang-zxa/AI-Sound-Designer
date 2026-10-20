"""Render measured artifacts only; never fits a model or performs inference."""
import json
import os
from pathlib import Path
import numpy as np
from generate_dataset import ROOT,sha256


def report():
    run=ROOT/'ml/runs/first_experiment';results=json.loads((run/'results.json').read_text())
    summaries={name:json.loads((run/name/'summary.json').read_text()) for name in ['cnn','shuffled']}
    data=Path(results['run']['dataset_directory']);audit=json.loads((data/'data_audit.json').read_text())
    lines=['# First offline parameter-prediction experiment — measured results','',
           'One fixed CNN and one shuffled-label control. No tuning or additional run followed test evaluation.','',
           '## Held-out test (300 examples)','',
           '| Method | Cutoff MAE (Hz) | Cutoff RMSE (Hz) | Attack MAE (ms) | Attack RMSE (ms) | Release MAE (ms) | Release RMSE (ms) | Normalized MSE |',
           '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for name in ['training_mean','dsp','cnn','shuffled']:
        metrics=results['test'][name];p=metrics['parameters'];values=[p[k][metric] for k in ['cutoff','attack','release'] for metric in ['mae','rmse']]+[metrics['normalized_mse']]
        lines.append('| '+name+' | '+' | '.join(format(v,'.12g') for v in values)+' |')
    lines+=['','Full floating-point metrics are retained in `runs/first_experiment/results.json`; predictions are in `test_predictions.csv` and `test_predictions.npz`. CSV physical cutoff values are Hz and attack/release values are seconds; the table converts envelope errors to ms.','',
            '## Baseline comparison','']
    for parameter in ['cutoff','attack','release']:
        neural=results['test']['cnn']['parameters'][parameter]['mae'];dsp=results['test']['dsp']['parameters'][parameter]['mae']
        winner='DSP baseline' if dsp<=neural else 'CNN'
        lines.append(f'- {parameter}: **{winner} has lower test MAE** (CNN {neural:.12g}, DSP {dsp:.12g}, in the table’s units).')
    best='DSP baseline' if results['test']['dsp']['normalized_mse']<=results['test']['cnn']['normalized_mse'] else 'CNN'
    lines += [f'- Overall normalized MSE: **{best} is lower**.','',
              'The DSP predictor uses three audio-derived scalar measurements and training-only calibration tables. It is not an uncalibrated closed-form estimator. A fixed pitch and waveform make spectral centroid particularly informative; this result cannot establish generalization to other pitches, velocities, waveforms or real recordings.','',
              '## Shuffled-label leakage sanity check','',
              f"Shuffled/control test normalized MSE divided by real-CNN MSE: **{results['shuffled_label_sanity']['test_mse_ratio_shuffled_over_cnn']:.12g}×**.",
              'Training target vectors alone were permuted with seed 20261021. Validation and test labels remained correct. The initial weights and batch-order seed match the main experiment. This is a pipeline sanity check, not proof of the absence of every possible leakage mechanism.','',
              '## Training and validation selection','',
              '| Condition | Epochs completed | Selected epoch | Best validation normalized MSE | Training seconds |','| --- | ---: | ---: | ---: | ---: |']
    for name,s in summaries.items():lines.append(f"| {name} | {s['epochs_completed']} | {s['best_epoch']} | {s['best_validation_normalized_mse']:.12g} | {s['training_seconds']:.12g} |")
    lines += ['','Both checkpoints were selected solely by validation MSE. Exactly one inference pass per selected checkpoint was made on the untouched test split. No checkpoint selection used test results.','',
              '## Offline inference latency','',
              '| Condition | Mean (ms) | Median (ms) | p95 (ms) | Minimum (ms) |','| --- | ---: | ---: | ---: | ---: |']
    for name,t in results['offline_latency'].items():lines.append('| '+name+' | '+' | '.join(format(t[k],'.12g') for k in ['mean_ms','median_ms','p95_ms','minimum_ms'])+' |')
    lines+=['','CPU, four Torch threads, batch size one, 30 warmups, 200 measurements on a validation example. Forward pass only: excludes WAV I/O, log-mel extraction and preprocessing. No real-time deployment claim.','',
            '## Data and leakage audit','',
            '- 3000 unique rendered audio/target vectors; 2400/300/300 split; finite, unclipped, four-second 48 kHz mono audio.',
            '- Waveform-only log-mel inputs `[B,1,64,747]`; targets `[B,3]`. Model `forward(x)` accepts no labels, IDs, paths or metadata.',
            '- Tests change labels, manifest contents and filenames and verify identical model inputs and forward outputs.',
            '- Three cached train/validation inputs were recomputed directly from WAV bytes and matched exactly.',
            '- Preprocessing statistics were independently recomputed from all 2400 training feature tensors only and matched exactly.',
            '- DSP windows depend only on the waveform and fixed note timing; true attack/release values are not used to select measurement windows.',
            '- Training-only means and DSP tables were frozen before CNN fitting. Neither training condition loaded the test split.',
            '- Plugin runtime sources were not modified; no model, Python, inference or networking was added to the plugin callback.','',
            '## Provenance','',
            f"Base Git commit: `{results['run']['provenance']['git_commit']}`; working-tree status and source fingerprints are preserved in `runs/first_experiment/run.json`.",
            f"Dataset manifest SHA-256: `{results['run']['dataset_manifest_sha256']}`.",
            f"Preprocessing SHA-256: `{results['run']['preprocessing_sha256']}`.",
            f"PyTorch {results['run']['torch_version']}; Python {results['run']['python_version']}; CPU architecture {results['run']['machine']}.",
            '', '## Interpretation and stop point','',
            'These measured results apply only to the approved controlled single-pitch, single-waveform experiment. Parameter estimation error is technical evidence; no perceptual preference or audio-similarity outcome is inferred. The next decision belongs to the user; no follow-up model or harder dataset has been started.']
    (ROOT/'ml/FIRST_EXPERIMENT_RESULTS.md').write_text('\n'.join(lines)+'\n')
    os.environ.setdefault('MPLCONFIGDIR',str(run/'matplotlib-cache'))
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(14,4),layout='constrained')
    methods=['training_mean','dsp','cnn','shuffled']
    for ax,parameter in zip(axes,['cutoff','attack','release']):
        x=np.arange(4);mae=[results['test'][m]['parameters'][parameter]['mae'] for m in methods];rmse=[results['test'][m]['parameters'][parameter]['rmse'] for m in methods]
        ax.bar(x-.18,mae,.36,label='MAE');ax.bar(x+.18,rmse,.36,label='RMSE');ax.set(xticks=x,xticklabels=['Mean','DSP','CNN','Shuffled'],yscale='log',title=parameter,ylabel='Hz' if parameter=='cutoff' else 'ms');ax.legend()
    fig.savefig(run/'test_errors.png',dpi=130);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    for ax,name in zip(axes,['cnn','shuffled']):
        history=json.loads((run/name/'history.json').read_text())
        for key in ['train_normalized_mse','validation_normalized_mse']:ax.plot([h['epoch'] for h in history],[h[key] for h in history],label=key)
        ax.axvline(summaries[name]['best_epoch'],color='grey',linestyle='--',label='selected epoch');ax.set(title=name,xlabel='Epoch',ylabel='Normalized MSE',yscale='log');ax.legend()
    fig.savefig(run/'learning_curves.png',dpi=130);plt.close(fig)
    print('Measured report saved to ml/FIRST_EXPERIMENT_RESULTS.md; no further experiment started.')


if __name__=='__main__':report()
