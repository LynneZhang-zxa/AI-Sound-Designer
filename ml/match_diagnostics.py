"""Internal, offline reference/reconstruction diagnostics; never a plugin visualizer."""
from pathlib import Path
import json
import numpy as np
from reference_match import representation, FEATURES


def save_diagnostics(folder,reference,candidate,frames):
    folder=Path(folder)
    r,re=representation(reference,frames);c,ce=representation(candidate,frames)
    # Both arrays use the matcher's comparison RMS alignment. Raw WAVs are retained separately.
    db_r=r[0]*10/np.log(10);db_c=c[0]*10/np.log(10)
    ceiling=float(max(db_r.max(),db_c.max()));floor=ceiling-80
    np.savez_compressed(folder/'spectrograms.npz',reference_log_power=r,reconstruction_log_power=c,
                        reference_envelope=re,reconstruction_envelope=ce)
    import os
    from generate_dataset import ROOT
    os.environ.setdefault("MPLCONFIGDIR",str(ROOT/"ml/runs/.match-plot-cache"))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(3,1,figsize=(10,8),layout='constrained')
    extent=(0,frames/24000,0,FEATURES['n_mels'])
    for ax,data,title in zip(axes[:2],[db_r,db_c],['Reference','Reconstruction']):
        im=ax.imshow(data,origin='lower',aspect='auto',extent=extent,vmin=floor,vmax=ceiling,cmap='magma')
        ax.set(title=title,ylabel='Mel band (not Hz)');fig.colorbar(im,ax=ax,label='Comparison dB power')
    t=np.arange(len(re))*.01
    axes[2].plot(t,re,label='Reference');axes[2].plot(t,ce,label='Reconstruction')
    axes[2].set(xlabel='Seconds',ylabel='Normalized envelope');axes[2].legend()
    fig.suptitle('Internal match diagnostic — common scale, RMS-aligned comparison; not raw levels')
    fig.savefig(folder/'spectrograms.png',dpi=120);plt.close(fig)
    info={'sample_rate':24000,'features':FEATURES,'frames':frames,'scale_db':[floor,ceiling],
          'level_policy':'Both comparison representations RMS aligned; identical color scale. Original reference.wav and matched.wav are not overwritten.',
          'limits':'Spectral/envelope diagnostics, not a perceptual score or independent evidence of exact parameter recovery.'}
    (folder/'diagnostics.json').write_text(json.dumps(info,indent=2)+'\n')
    return {'arrays':'spectrograms.npz','image':'spectrograms.png','metadata':'diagnostics.json'}
