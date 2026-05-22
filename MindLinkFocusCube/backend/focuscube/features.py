import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass

import numpy as np
from scipy.integrate import simpson
from scipy.signal import butter, filtfilt, iirnotch, welch

from .config import FocusCubeConfig


EEG_BANDS = {
    "delta": (0.5, 4),
    "theta": (4, 8),
    "alpha": (8, 12),
    "beta": (12, 30),
    "gamma": (30, 45),
}


@dataclass(frozen=True)
class BandFeatures:
    bands: dict[str, float]
    relative: dict[str, float]
    total_power: float
    quality: float


class AdaptiveNormalizer:
    def __init__(self, window: int = 120) -> None:
        self.window = window
        self._values: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=window))

    def normalize(self, key: str, value: float) -> float:
        if not math.isfinite(value):
            value = 0.0

        values = self._values[key]
        values.append(float(value))
        low = min(values)
        high = max(values)

        if math.isclose(high, low):
            return 0.5 if len(values) == 1 else 0.0

        return clamp((value - low) / (high - low))


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def bandpass_filter(data: np.ndarray, fs: int) -> np.ndarray:
    nyquist = fs * 0.5
    b, a = butter(2, [1.0 / nyquist, 45.0 / nyquist], btype="band")
    return filtfilt(b, a, data)


def notch_filter(data: np.ndarray, fs: int) -> np.ndarray:
    b, a = iirnotch(50.0 / (fs * 0.5), 30.0)
    return filtfilt(b, a, data)


def bandpower(psd: np.ndarray, freqs: np.ndarray, band: str) -> float:
    low, high = EEG_BANDS[band]
    idx = np.logical_and(freqs >= low, freqs <= high)
    if not np.any(idx):
        return 0.0
    return float(simpson(psd[idx], x=freqs[idx]))


def signal_quality(data: np.ndarray) -> float:
    if len(data) == 0:
        return 0.0
    std = float(np.std(data))
    if std < 0.1:
        return 0.0
    if std > 5000:
        return 0.2
    return clamp(std / 25.0)


def compute_band_features(raw_samples, config: FocusCubeConfig | None = None) -> BandFeatures:
    config = config or FocusCubeConfig()
    data = np.asarray(raw_samples, dtype=float)

    if data.size < config.window_size:
        raise ValueError(f"Need at least {config.window_size} raw samples")

    data = data[-max(config.window_size * 3, config.window_size):]
    data = data - np.mean(data)
    filtered = bandpass_filter(notch_filter(data, config.sample_rate), config.sample_rate)
    freqs, psd = welch(
        filtered,
        fs=config.sample_rate,
        nperseg=config.window_size,
        noverlap=config.overlap_size,
    )

    bands = {name: bandpower(psd, freqs, name) for name in EEG_BANDS}
    total_power = float(simpson(psd, x=freqs))
    relative = {
        name: (power / total_power if total_power > 0 else 0.0)
        for name, power in bands.items()
    }

    return BandFeatures(
        bands=bands,
        relative=relative,
        total_power=total_power,
        quality=signal_quality(filtered),
    )


def attention_from_normalized(normalized: dict[str, float], config: FocusCubeConfig) -> float:
    source = config.attention_source
    alpha = clamp(normalized.get("alpha", 0.0))
    beta = clamp(normalized.get("beta", 0.0))
    gamma = clamp(normalized.get("gamma", 0.0))

    if source == "inverse_alpha":
        return clamp(1.0 - alpha)
    if source == "beta_alpha_ratio":
        return clamp((beta + 0.25 * gamma) / (alpha + beta + 0.25 * gamma + 1e-9))
    return alpha


def build_payload(
    features: BandFeatures,
    normalizer: AdaptiveNormalizer,
    config: FocusCubeConfig,
    mode: str,
    device_status: dict | None = None,
) -> dict:
    normalized = {
        "alpha": normalizer.normalize("alpha", features.bands["alpha"]),
        "beta": normalizer.normalize("beta", features.bands["beta"]),
        "gamma": normalizer.normalize("gamma", features.bands["gamma"]),
    }
    normalized["betaGamma"] = clamp((normalized["beta"] + normalized["gamma"]) * 0.5)

    payload = {
        "timestamp": time.time(),
        "mode": mode,
        "quality": features.quality,
        "attention": attention_from_normalized(normalized, config),
        "bands": {
            "alpha": features.bands["alpha"],
            "beta": features.bands["beta"],
            "gamma": features.bands["gamma"],
        },
        "relative": {
            "alpha": features.relative["alpha"],
            "beta": features.relative["beta"],
            "gamma": features.relative["gamma"],
        },
        "normalized": normalized,
    }
    if device_status:
        payload["device"] = dict(device_status)
    return payload


def demo_frame(t: float, config: FocusCubeConfig | None = None) -> dict:
    config = config or FocusCubeConfig()
    alpha = 0.5 + 0.42 * math.sin(t * 1.4)
    beta = 0.45 + 0.30 * math.sin(t * 2.1 + 1.7)
    gamma = 0.30 + 0.22 * math.sin(t * 3.2 + 0.5)
    normalized = {
        "alpha": clamp(alpha),
        "beta": clamp(beta),
        "gamma": clamp(gamma),
    }
    normalized["betaGamma"] = clamp((normalized["beta"] + normalized["gamma"]) * 0.5)

    return {
        "timestamp": time.time(),
        "mode": "demo",
        "device": {
            "connected": False,
            "port": None,
            "battery": None,
            "firmwareVersion": None,
            "sampleCount": 0,
        },
        "quality": 0.85,
        "attention": attention_from_normalized(normalized, config),
        "bands": {
            "alpha": 10.0 + normalized["alpha"] * 25.0,
            "beta": 6.0 + normalized["beta"] * 18.0,
            "gamma": 2.0 + normalized["gamma"] * 10.0,
        },
        "relative": {
            "alpha": normalized["alpha"] * 0.45,
            "beta": normalized["beta"] * 0.35,
            "gamma": normalized["gamma"] * 0.20,
        },
        "normalized": normalized,
    }


def warming_frame(
    config: FocusCubeConfig,
    sample_count: int,
    device_status: dict | None = None,
) -> dict:
    normalized = {
        "alpha": 0.0,
        "beta": 0.0,
        "gamma": 0.0,
        "betaGamma": 0.0,
    }
    status = {
        "connected": True,
        "port": None,
        "battery": None,
        "firmwareVersion": None,
        "sampleCount": int(sample_count),
    }
    if device_status:
        status.update(device_status)
    status["sampleCount"] = int(sample_count)

    return {
        "timestamp": time.time(),
        "mode": "device_warming",
        "device": status,
        "quality": 0.0,
        "attention": 0.5,
        "sampleCount": int(sample_count),
        "requiredSamples": config.window_size,
        "bands": {
            "alpha": 0.0,
            "beta": 0.0,
            "gamma": 0.0,
        },
        "relative": {
            "alpha": 0.0,
            "beta": 0.0,
            "gamma": 0.0,
        },
        "normalized": normalized,
    }
