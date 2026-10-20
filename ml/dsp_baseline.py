"""Three waveform-only DSP measurements, with frozen training-only calibration."""
import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import welch


def measure(audio, rate, timing):
    on, off = round(timing["note_on_seconds"] * rate), round(timing["note_off_seconds"] * rate)
    envelope = np.sqrt(np.maximum(0, uniform_filter1d(np.asarray(audio) ** 2, size=round(.02 * rate), mode="constant")))
    # Fixed windows: never read ground-truth attack/release/cutoff here.
    held = envelope[on:off]
    peak = np.max(held)
    crossing = lambda values, threshold: int(np.flatnonzero(values >= threshold)[0])
    rise = (crossing(held, .9 * peak) - crossing(held, .1 * peak)) / rate
    plateau = np.median(envelope[off-round(.15*rate):off-round(.03*rate)])
    tail = envelope[off:]
    fall90 = int(np.flatnonzero(tail <= .9 * plateau)[0])
    fall10 = int(np.flatnonzero(tail <= .1 * plateau)[0])
    fall = (fall10 - fall90) / rate
    f, power = welch(audio[round(1.*rate):round(1.4*rate)], fs=rate, nperseg=4096)
    centroid = np.sum(f * power) / np.sum(power)
    return np.array([centroid, rise, fall], dtype=np.float64)


class DSPBaseline:
    """Monotone-axis 1-D interpolation: one scalar proxy per target, no CNN features.

    Training-only lookup calibration handles the nonlinear centroid/cutoff relationship
    without choosing polynomial degree or running a parameter search. Duplicate proxy
    values are averaged. Out-of-training-range proxies use endpoint predictions.
    """
    def fit(self, proxies, physical_targets):
        self.tables = []
        for column in range(3):
            x, inverse = np.unique(proxies[:, column], return_inverse=True)
            y = np.bincount(inverse, weights=physical_targets[:, column]) / np.bincount(inverse)
            self.tables.append((x, y))
        return self

    def predict(self, proxies):
        return np.stack([np.interp(proxies[:, i], x, y) for i, (x, y) in enumerate(self.tables)], axis=1)

    def serializable(self):
        return {"calibration_split":"train", "method":"three independent 1D interpolation tables", "tables":[{"proxy":x.tolist(),"physical_target":y.tolist()} for x,y in self.tables]}
