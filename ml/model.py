"""The sole CNN architecture for the real run and shuffled-label control."""
import torch
from torch import nn


class ParameterCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.network = nn.Sequential(
            nn.Conv2d(1,16,3,stride=2,padding=1), nn.ReLU(),
            nn.Conv2d(16,32,3,stride=2,padding=1), nn.ReLU(),
            nn.AdaptiveAvgPool2d((4,16)), nn.Flatten(),
            nn.Linear(32*4*16,64), nn.ReLU(), nn.Linear(64,3), nn.Sigmoid())

    def forward(self, x):
        # No metadata, IDs, targets, filenames or DSP proxies enter forward().
        if x.ndim != 4 or tuple(x.shape[1:]) != (1,64,747) or not torch.is_floating_point(x):
            raise ValueError('Expected waveform-derived log-mel tensor [B,1,64,747]')
        return self.network(x)
