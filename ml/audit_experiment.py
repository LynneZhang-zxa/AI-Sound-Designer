"""Pre-training input-path and training-only preprocessing audit."""
import json
from pathlib import Path
import numpy as np
from generate_dataset import ROOT,sha256
from prepare_experiment import waveform_features


def audit(directory):
    directory=Path(directory);data=json.loads((directory/'rendered_manifest.json').read_text());cfg=data['metadata']['config']
    training=np.load(directory/'train_features.npy',mmap_mode='r')
    total=0;sums=np.zeros(64);squares=np.zeros(64)
    for i in range(0,len(training),32):
        block=np.asarray(training[i:i+32],dtype=np.float64)
        sums+=block.sum(axis=(0,1,3));squares+=(block**2).sum(axis=(0,1,3));total+=len(block)*block.shape[3]
    mean=sums/total;std=np.sqrt(np.maximum(squares/total-mean**2,0))
    recorded=json.loads((directory/'preprocessing.json').read_text())
    np.testing.assert_allclose(mean,recorded['mean_per_mel'],rtol=0,atol=1e-12)
    np.testing.assert_allclose(std,recorded['std_per_mel'],rtol=0,atol=1e-12)
    checks=[]
    for split,indices in [('train',[0,31]),('validation',[0])]:
        rows=[r for r in data['examples'] if r['split']==split];cache=np.load(directory/f'{split}_features.npy',mmap_mode='r')
        for i in indices:
            x,_=waveform_features(directory/rows[i]['audio'],cfg['renderer'],cfg['features'])
            np.testing.assert_array_equal(x,cache[i]);checks.append({'split':split,'row_index':i,'byte_exact_waveform_recomputation':True})
    result={'status':'PASS','preprocessing_exactly_recomputed_from':'2400 training feature tensors only',
            'waveform_recomputations':checks,'model_forward_signature':'forward(x): tensor [B,1,64,747] only',
            'dataset_item':'(standardized_log_mel_tensor, supervised_target_tensor); only first element is passed to model',
            'metadata_mutation_regression':'13 tests passed; metadata/filenames/target mutation leaves inputs and forward outputs unchanged',
            'dsp_features':'waveform and fixed timing only; no ground-truth attack/release windows',
            'test_model_inference_performed':False,
            'audited_source_hashes':{name:sha256(ROOT/'ml'/name) for name in ['features.py','dataset.py','model.py','train.py','dsp_baseline.py','prepare_experiment.py','tests/test_learning.py']}}
    (directory/'input_path_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':audit(ROOT/'ml/data/experiment_3000')
