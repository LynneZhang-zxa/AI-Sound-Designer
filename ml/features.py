"""Offline HTK log-mel power; preserves absolute level (no clip normalization)."""
import numpy as np
from scipy.signal.windows import hann


def log_mel(audio, rate, config):
    if config["center"] or config["mel_scale"] != "htk":
        raise ValueError("Only non-centered HTK features are specified")
    n_fft, hop = config["n_fft"], config["hop_length"]
    audio = np.asarray(audio, dtype=np.float64)
    if audio.ndim != 1 or len(audio) < n_fft or not np.isfinite(audio).all():
        raise ValueError("Invalid waveform")
    frames = np.lib.stride_tricks.sliding_window_view(audio, n_fft)[::hop]
    # Scale by window energy; convention is fixed in the dataset config.
    window = hann(n_fft, sym=False)
    power = np.abs(np.fft.rfft(frames * window, axis=-1)) ** 2 / np.sum(window ** 2)
    hz_to_mel = lambda hz: 2595.0 * np.log10(1.0 + np.asarray(hz) / 700.0)
    mel_to_hz = lambda mel: 700.0 * (10.0 ** (mel / 2595.0) - 1.0)
    edges = mel_to_hz(np.linspace(hz_to_mel(config["fmin"]), hz_to_mel(config["fmax"]), config["n_mels"] + 2))
    if not 0 <= config["fmin"] < config["fmax"] <= rate / 2:
        raise ValueError("Invalid mel frequency bounds")
    frequencies = np.fft.rfftfreq(n_fft, 1 / rate)
    bank = []
    for low, mid, high in zip(edges, edges[1:], edges[2:]):
        triangle = np.maximum(0, np.minimum((frequencies - low) / (mid - low), (high - frequencies) / (high - mid)))
        if not np.any(triangle):
            raise ValueError("FFT too small for mel bank")
        bank.append(triangle * (2.0 / (high - low)))  # Area normalization, not recording normalization.
    mel_power = np.asarray(bank) @ power.T
    return np.log(np.maximum(mel_power, config["log_floor"])).astype(np.float32)[None, :, :]
