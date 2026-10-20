"""Supervised pairs only: loader returns (features, target); forward gets features."""
import json
from pathlib import Path
import numpy as np
import torch
from torch.utils.data import Dataset


class LogMelDataset(Dataset):
    def __init__(self, directory, split, permutation=None):
        directory=Path(directory)
        self.features=np.load(directory/f'{split}_features.npy',mmap_mode='r')
        self.targets=np.load(directory/f'{split}_targets.npy')
        stats=json.loads((directory/'preprocessing.json').read_text())
        if stats['source_split']!='train': raise ValueError('Preprocessing must be fitted on training data')
        self.mean=np.asarray(stats['mean_per_mel'],dtype=np.float32)[None,:,None]
        self.std=np.maximum(np.asarray(stats['std_per_mel'],dtype=np.float32)[None,:,None],1e-6)
        if permutation is not None:
            if split!='train' or sorted(permutation.tolist()) != list(range(len(self.targets))):
                raise ValueError('Only a complete training-label permutation is allowed')
            self.targets=self.targets[permutation].copy()
        if self.features.shape[1:]!=(1,64,747) or self.targets.shape!=(len(self.features),3):
            raise ValueError('Unexpected feature/target shapes')

    def __len__(self): return len(self.targets)

    def __getitem__(self,index):
        x=(np.asarray(self.features[index])-self.mean)/self.std
        # Metadata and filenames are not stored on this object.
        return torch.from_numpy(x.copy()),torch.from_numpy(self.targets[index].copy())
