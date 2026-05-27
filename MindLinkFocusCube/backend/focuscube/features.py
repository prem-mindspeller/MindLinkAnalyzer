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
    metrics: dict[str, float] | None = None


@dataclass(frozen=True)
class ChannelFocusFeatures:
    channel_features: dict[int, BandFeatures]
    regions: dict[str, BandFeatures]
    metrics: dict[str, float]


@dataclass(frozen=True)
class FocusIndex:
    attention: float
    smoothed_attention: float
    mode: str
    components: dict[str, float]
    baseline_progress: float
    baseline_count: int
    baseline_required: int


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


def frequency_power(psd: np.ndarray, freqs: np.ndarray, low: float, high: float) -> float:
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

    return band_features_from_psd(psd, freqs, filtered)


def band_features_from_psd(psd: np.ndarray, freqs: np.ndarray, filtered: np.ndarray) -> BandFeatures:
    bands = {name: bandpower(psd, freqs, name) for name in EEG_BANDS}
    total_power = float(simpson(psd, x=freqs))
    relative = {
        name: (power / total_power if total_power > 0 else 0.0)
        for name, power in bands.items()
    }
    hf_power = frequency_power(psd, freqs, 30, 45)
    line_power = frequency_power(psd, freqs, 49, 51) + frequency_power(psd, freqs, 59, 61)
    metrics = {
        "highFrequencyRatio": hf_power / (total_power + 1e-12),
        "lineNoiseRatio": line_power / (total_power + 1e-12),
        "alphaThetaRatio": bands["alpha"] / (bands["theta"] + 1e-12),
        "betaAlphaRatio": bands["beta"] / (bands["alpha"] + 1e-12),
        "engagement": bands["beta"] / (bands["alpha"] + bands["theta"] + 1e-12),
    }

    return BandFeatures(
        bands=bands,
        relative=relative,
        total_power=total_power,
        quality=signal_quality(filtered),
        metrics=metrics,
    )


class ChannelBandFeatureExtractor:
    def __init__(
        self,
        config: FocusCubeConfig | None = None,
        frontal_rows: tuple[int, ...] = (0, 1),
        occipital_rows: tuple[int, ...] = (4, 5),
    ) -> None:
        self.config = config or FocusCubeConfig()
        self.frontal_rows = tuple(int(row) for row in frontal_rows)
        self.occipital_rows = tuple(int(row) for row in occipital_rows)

    def compute(self, channel_samples: dict[int, list[float] | np.ndarray]) -> ChannelFocusFeatures:
        channel_features = {
            int(row): compute_band_features(samples, self.config)
            for row, samples in channel_samples.items()
            if len(samples) >= self.config.window_size
        }
        regions = {
            "frontal": self._region_features(channel_samples, self.frontal_rows),
            "occipital": self._region_features(channel_samples, self.occipital_rows),
            "all": self._region_features(channel_samples, tuple(channel_samples.keys())),
        }
        metrics = self._metrics(regions)
        return ChannelFocusFeatures(
            channel_features=channel_features,
            regions={name: feature for name, feature in regions.items() if feature is not None},
            metrics=metrics,
        )

    def _region_features(
        self,
        channel_samples: dict[int, list[float] | np.ndarray],
        rows: tuple[int, ...],
    ) -> BandFeatures | None:
        available = [
            np.asarray(channel_samples[row], dtype=float)[-self.config.window_size * 3:]
            for row in rows
            if row in channel_samples and len(channel_samples[row]) >= self.config.window_size
        ]
        if not available:
            return None
        min_len = min(len(values) for values in available)
        merged = np.mean([values[-min_len:] for values in available], axis=0)
        return compute_band_features(merged, self.config)

    def _metrics(self, regions: dict[str, BandFeatures | None]) -> dict[str, float]:
        frontal = regions.get("frontal")
        occipital = regions.get("occipital")
        all_region = regions.get("all")
        metrics = {
            "frontalEngagement": _metric(frontal, "engagement"),
            "frontalAlpha": _band(frontal, "alpha"),
            "frontalTheta": _band(frontal, "theta"),
            "frontalBeta": _band(frontal, "beta"),
            "occipitalAlpha": _band(occipital, "alpha"),
            "occipitalBeta": _band(occipital, "beta"),
            "highFrequencyRatio": _metric(all_region, "highFrequencyRatio"),
            "lineNoiseRatio": _metric(all_region, "lineNoiseRatio"),
            "quality": all_region.quality if all_region else 0.0,
        }
        return metrics


class FocusIndexEstimator:
    def __init__(self, config: FocusCubeConfig | None = None) -> None:
        self.config = config or FocusCubeConfig()
        self._baseline: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=self.config.calibration_windows))
        self._smoothed_attention = 0.0
        self._calibrated = False

    def update(self, features: ChannelFocusFeatures) -> FocusIndex:
        metrics = features.metrics
        if not self._calibrated:
            for key in _baseline_metric_keys():
                self._baseline[key].append(float(metrics.get(key, 0.0)))
            baseline_count = min(len(values) for values in self._baseline.values())
            baseline_required = max(1, self.config.calibration_windows)
            progress = min(1.0, baseline_count / baseline_required)
            if progress >= 1.0:
                self._calibrated = True
            return FocusIndex(
                attention=0.0,
                smoothed_attention=0.0,
                mode="device" if self._calibrated else "device_calibrating",
                components={
                    "frontalEngagement": 0.0,
                    "occipitalAlphaSuppression": 0.0,
                    "frontalAlphaSuppression": 0.0,
                    "occipitalAlphaActivation": 0.0,
                    "artifactPenalty": self._artifact_penalty(metrics),
                },
                baseline_progress=progress,
                baseline_count=baseline_count,
                baseline_required=baseline_required,
            )

        components = self._score_components(metrics)
        artifact_penalty = self._artifact_penalty(metrics)
        focus_attention = clamp(
            self.config.focus_engagement_weight * components["frontalEngagement"]
            + self.config.focus_occipital_alpha_weight * components["occipitalAlphaSuppression"]
            + self.config.focus_frontal_alpha_weight * components["frontalAlphaSuppression"]
        )
        alpha_attention = clamp(
            self.config.focus_alpha_activation_weight
            * components["occipitalAlphaActivation"]
        )
        raw_attention = max(focus_attention, alpha_attention)
        attention = clamp(raw_attention * artifact_penalty)
        self._smoothed_attention = (
            self._smoothed_attention * (1.0 - self.config.focus_smoothing)
            + attention * self.config.focus_smoothing
        )
        components["artifactPenalty"] = artifact_penalty
        return FocusIndex(
            attention=clamp(attention),
            smoothed_attention=clamp(self._smoothed_attention),
            mode="device",
            components=components,
            baseline_progress=1.0,
            baseline_count=max(1, self.config.calibration_windows),
            baseline_required=max(1, self.config.calibration_windows),
        )

    def reset(self) -> None:
        self._baseline.clear()
        self._smoothed_attention = 0.0
        self._calibrated = False

    def _score_components(self, metrics: dict[str, float]) -> dict[str, float]:
        return {
            "frontalEngagement": positive_z_score(
                metrics.get("frontalEngagement", 0.0),
                self._baseline_values("frontalEngagement"),
                self.config,
            ),
            "occipitalAlphaSuppression": negative_z_score(
                metrics.get("occipitalAlpha", 0.0),
                self._baseline_values("occipitalAlpha"),
                self.config,
            ),
            "occipitalAlphaActivation": positive_z_score(
                metrics.get("occipitalAlpha", 0.0),
                self._baseline_values("occipitalAlpha"),
                self.config,
            ),
            "frontalAlphaSuppression": negative_z_score(
                metrics.get("frontalAlpha", 0.0),
                self._baseline_values("frontalAlpha"),
                self.config,
            ),
        }

    def _artifact_penalty(self, metrics: dict[str, float]) -> float:
        hf = metrics.get("highFrequencyRatio", 0.0)
        line = metrics.get("lineNoiseRatio", 0.0)
        quality = metrics.get("quality", 0.0)
        hf_penalty = 1.0 - clamp((hf - self.config.artifact_hf_ratio_threshold) / 0.25)
        line_penalty = 1.0 - clamp((line - self.config.artifact_line_ratio_threshold) / 0.20)
        quality_penalty = 0.35 + 0.65 * clamp(quality)
        return clamp(min(hf_penalty, line_penalty, quality_penalty))

    def _baseline_values(self, key: str) -> list[float]:
        return list(self._baseline[key])


def positive_z_score(value: float, baseline: list[float], config: FocusCubeConfig | None = None) -> float:
    config = config or FocusCubeConfig()
    center, spread = robust_center_spread(baseline)
    z = (value - center) / spread
    z_score = clamp((z - 0.25) / 1.75)
    pct_score = positive_percent_change_score(value, center, config)
    return max(z_score, pct_score)


def negative_z_score(value: float, baseline: list[float], config: FocusCubeConfig | None = None) -> float:
    config = config or FocusCubeConfig()
    center, spread = robust_center_spread(baseline)
    z = (center - value) / spread
    z_score = clamp((z - 0.25) / 1.75)
    pct_score = negative_percent_change_score(value, center, config)
    return max(z_score, pct_score)


def positive_percent_change_score(value: float, center: float, config: FocusCubeConfig) -> float:
    denom = abs(center) + 1e-9
    change = (value - center) / denom
    return clamp((change - config.focus_deadband) / config.focus_percent_change_full_scale)


def negative_percent_change_score(value: float, center: float, config: FocusCubeConfig) -> float:
    denom = abs(center) + 1e-9
    change = (center - value) / denom
    return clamp((change - config.focus_deadband) / config.focus_percent_change_full_scale)


def robust_center_spread(values: list[float]) -> tuple[float, float]:
    data = np.asarray(values, dtype=float)
    if data.size == 0:
        return 0.0, 1.0
    center = float(np.median(data))
    mad = float(np.median(np.abs(data - center)))
    spread = max(mad * 1.4826, abs(center) * 0.08, 1e-9)
    return center, spread


def _baseline_metric_keys() -> tuple[str, ...]:
    return ("frontalEngagement", "frontalAlpha", "occipitalAlpha")


def _band(feature: BandFeatures | None, band: str) -> float:
    if feature is None:
        return 0.0
    return float(feature.bands.get(band, 0.0))


def _metric(feature: BandFeatures | None, key: str) -> float:
    if feature is None or feature.metrics is None:
        return 0.0
    return float(feature.metrics.get(key, 0.0))


def attention_from_normalized(normalized: dict[str, float], config: FocusCubeConfig) -> float:
    source = config.attention_source
    if source == "focus_index":
        return clamp(normalized.get("focusIndex", normalized.get("alpha", 0.0)))
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
    normalized["focusIndex"] = normalized["alpha"]

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
            "source": "demo",
            "deviceName": "Synthetic MindRove",
            "ipAddress": None,
            "ipPort": None,
            "serialPort": None,
            "battery": None,
            "sampleRate": config.sample_rate,
            "eegChannels": [],
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
        "source": "mindrove",
        "deviceName": "MindRove Bright",
        "ipAddress": None,
        "ipPort": None,
        "serialPort": None,
        "battery": None,
        "sampleRate": config.sample_rate,
        "eegChannels": [],
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
        "attention": 0.0,
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


def not_worn_frame(
    config: FocusCubeConfig,
    sample_count: int,
    device_status: dict | None = None,
) -> dict:
    payload = warming_frame(config, sample_count, device_status)
    payload["mode"] = "device_not_worn"
    payload["attention"] = 0.0
    payload["quality"] = 0.0
    payload["sampleCount"] = int(sample_count)
    payload["device"]["worn"] = False
    return payload
