import asyncio

import numpy as np

from focuscube.config import FocusCubeConfig
from focuscube.features import (
    AdaptiveNormalizer,
    attention_from_normalized,
    build_payload,
    ChannelBandFeatureExtractor,
    FocusIndexEstimator,
    compute_band_features,
    demo_frame,
    warming_frame,
)


def sine_wave(freq, fs=500, seconds=3, amplitude=50):
    t = np.arange(0, seconds, 1 / fs)
    return amplitude * np.sin(2 * np.pi * freq * t)


def mixed_signal(components, fs=500, seconds=3):
    t = np.arange(0, seconds, 1 / fs)
    out = np.zeros_like(t)
    for freq, amplitude in components:
        out += amplitude * np.sin(2 * np.pi * freq * t)
    return out


def test_compute_band_features_detects_alpha_from_raw_samples():
    features = compute_band_features(sine_wave(10))

    assert features.bands["alpha"] > features.bands["beta"] * 4
    assert features.relative["alpha"] > 0.55


def test_channel_feature_extractor_keeps_bright_regions_separate():
    extractor = ChannelBandFeatureExtractor(FocusCubeConfig())
    samples = {
        0: sine_wave(18, seconds=3),
        1: sine_wave(18, seconds=3),
        4: sine_wave(10, seconds=3),
        5: sine_wave(10, seconds=3),
    }

    features = extractor.compute(samples)

    assert features.channel_features[0].relative["beta"] > 0.55
    assert features.channel_features[4].relative["alpha"] > 0.55
    assert features.regions["frontal"].relative["beta"] > 0.55
    assert features.regions["occipital"].relative["alpha"] > 0.55


def test_focus_index_requires_calibration_and_scores_engagement_against_baseline():
    config = FocusCubeConfig(calibration_windows=2, focus_smoothing=1.0)
    extractor = ChannelBandFeatureExtractor(config)
    estimator = FocusIndexEstimator(config)
    baseline_samples = {
        0: mixed_signal([(10, 45), (18, 8)], seconds=3),
        1: mixed_signal([(10, 45), (18, 8)], seconds=3),
        4: mixed_signal([(10, 55), (18, 6)], seconds=3),
        5: mixed_signal([(10, 55), (18, 6)], seconds=3),
    }
    focus_samples = {
        0: mixed_signal([(10, 18), (18, 45)], seconds=3),
        1: mixed_signal([(10, 18), (18, 45)], seconds=3),
        4: mixed_signal([(10, 18), (18, 8)], seconds=3),
        5: mixed_signal([(10, 18), (18, 8)], seconds=3),
    }

    first = estimator.update(extractor.compute(baseline_samples))
    second = estimator.update(extractor.compute(baseline_samples))
    focused = estimator.update(extractor.compute(focus_samples))

    assert first.mode == "device_calibrating"
    assert first.baseline_count == 1
    assert first.baseline_required == 2
    assert second.mode == "device"
    assert second.baseline_count == 2
    assert second.baseline_required == 2
    assert focused.attention > 0.70
    assert focused.components["frontalEngagement"] > 0.70
    assert focused.components["occipitalAlphaSuppression"] > 0.70


def test_focus_index_stays_low_for_baseline_like_windows_after_calibration():
    config = FocusCubeConfig(calibration_windows=2, focus_smoothing=1.0)
    extractor = ChannelBandFeatureExtractor(config)
    estimator = FocusIndexEstimator(config)
    baseline_samples = {
        0: mixed_signal([(10, 45), (18, 8)], seconds=3),
        1: mixed_signal([(10, 45), (18, 8)], seconds=3),
        4: mixed_signal([(10, 55), (18, 6)], seconds=3),
        5: mixed_signal([(10, 55), (18, 6)], seconds=3),
    }

    estimator.update(extractor.compute(baseline_samples))
    estimator.update(extractor.compute(baseline_samples))
    stable = estimator.update(extractor.compute(baseline_samples))

    assert stable.mode == "device"
    assert stable.attention < 0.35


def test_focus_index_responds_to_moderate_realistic_percent_changes():
    config = FocusCubeConfig(
        calibration_windows=2,
        focus_smoothing=1.0,
        focus_percent_change_full_scale=0.25,
        focus_deadband=0.03,
    )
    extractor = ChannelBandFeatureExtractor(config)
    estimator = FocusIndexEstimator(config)
    baseline_samples = {
        0: mixed_signal([(10, 35), (18, 12)], seconds=3),
        1: mixed_signal([(10, 35), (18, 12)], seconds=3),
        4: mixed_signal([(10, 38), (18, 7)], seconds=3),
        5: mixed_signal([(10, 38), (18, 7)], seconds=3),
    }
    modest_focus_samples = {
        0: mixed_signal([(10, 30), (18, 16)], seconds=3),
        1: mixed_signal([(10, 30), (18, 16)], seconds=3),
        4: mixed_signal([(10, 30), (18, 7)], seconds=3),
        5: mixed_signal([(10, 30), (18, 7)], seconds=3),
    }

    estimator.update(extractor.compute(baseline_samples))
    estimator.update(extractor.compute(baseline_samples))
    focused = estimator.update(extractor.compute(modest_focus_samples))

    assert focused.attention > 0.15
    assert focused.components["frontalEngagement"] > 0.10
    assert focused.components["occipitalAlphaSuppression"] > 0.10


def test_focus_index_can_respond_to_occipital_alpha_activation():
    config = FocusCubeConfig(
        calibration_windows=2,
        focus_smoothing=1.0,
        focus_percent_change_full_scale=0.25,
        focus_deadband=0.03,
    )
    extractor = ChannelBandFeatureExtractor(config)
    estimator = FocusIndexEstimator(config)
    baseline_samples = {
        0: mixed_signal([(10, 25), (18, 10)], seconds=3),
        1: mixed_signal([(10, 25), (18, 10)], seconds=3),
        4: mixed_signal([(10, 25), (18, 7)], seconds=3),
        5: mixed_signal([(10, 25), (18, 7)], seconds=3),
    }
    alpha_samples = {
        0: mixed_signal([(10, 25), (18, 10)], seconds=3),
        1: mixed_signal([(10, 25), (18, 10)], seconds=3),
        4: mixed_signal([(10, 45), (18, 7)], seconds=3),
        5: mixed_signal([(10, 45), (18, 7)], seconds=3),
    }

    estimator.update(extractor.compute(baseline_samples))
    estimator.update(extractor.compute(baseline_samples))
    focused = estimator.update(extractor.compute(alpha_samples))

    assert focused.attention > 0.20
    assert focused.components["occipitalAlphaActivation"] > 0.20


def test_attention_mapping_uses_normalized_alpha_by_default():
    config = FocusCubeConfig(attention_source="alpha")

    assert attention_from_normalized({"alpha": 0.8, "beta": 0.1, "gamma": 0.1}, config) == 0.8


def test_attention_mapping_can_ignore_alpha_with_ratio_mode():
    config = FocusCubeConfig(attention_source="beta_alpha_ratio")

    value = attention_from_normalized({"alpha": 0.2, "beta": 0.8, "gamma": 0.1}, config)

    assert value > 0.75


def test_adaptive_normalizer_returns_bounded_values():
    normalizer = AdaptiveNormalizer(window=4)

    values = [normalizer.normalize("alpha", value) for value in [10, 20, 30, 40, 50]]

    assert all(0 <= value <= 1 for value in values)
    assert values[-1] == 1


def test_payload_shape_is_raw_feature_derived():
    config = FocusCubeConfig(attention_source="alpha")
    features = compute_band_features(sine_wave(10))
    normalizer = AdaptiveNormalizer(window=8)

    payload = build_payload(features, normalizer, config, mode="device")

    assert payload["mode"] == "device"
    assert "attention" in payload
    assert {"alpha", "beta", "gamma"}.issubset(payload["bands"])
    assert {"alpha", "beta", "gamma", "betaGamma"}.issubset(payload["normalized"])
    assert "parserAttention" not in payload
    assert "parserMeditation" not in payload


def test_payload_can_include_device_status_without_parser_attention():
    config = FocusCubeConfig(attention_source="alpha")
    features = compute_band_features(sine_wave(10))
    normalizer = AdaptiveNormalizer(window=8)

    payload = build_payload(
        features,
        normalizer,
        config,
        mode="device",
        device_status={
            "ipAddress": "192.168.4.1",
            "ipPort": 4210,
            "battery": 88,
            "deviceName": "MindRoveWifi",
            "sampleCount": 512,
        },
    )

    assert payload["device"]["ipAddress"] == "192.168.4.1"
    assert payload["device"]["ipPort"] == 4210
    assert payload["device"]["battery"] == 88
    assert payload["device"]["deviceName"] == "MindRoveWifi"
    assert payload["device"]["sampleCount"] == 512
    assert "parserAttention" not in payload


def test_demo_frame_emits_bounded_payload():
    payload = demo_frame(0.5, FocusCubeConfig())

    assert payload["mode"] == "demo"
    assert 0 <= payload["attention"] <= 1
    assert 0 <= payload["normalized"]["alpha"] <= 1


def test_warming_frame_is_not_demo_mode():
    payload = warming_frame(
        FocusCubeConfig(),
        sample_count=42,
        device_status={"ipAddress": "192.168.4.1", "ipPort": 4210, "battery": 88},
    )

    assert payload["mode"] == "device_warming"
    assert payload["sampleCount"] == 42
    assert payload["requiredSamples"] == FocusCubeConfig().window_size
    assert payload["device"]["ipAddress"] == "192.168.4.1"
    assert payload["device"]["ipPort"] == 4210
    assert payload["device"]["battery"] == 88
    assert payload["attention"] == 0.5
    assert "parserAttention" not in payload
    assert "parserMeditation" not in payload


def test_demo_stream_payload_omits_parser_attention_fields():
    from focuscube.server import create_frame_stream

    async def read_one():
        stream = create_frame_stream(FocusCubeConfig(), demo=True)
        try:
            return await anext(stream)
        finally:
            await stream.aclose()

    payload = asyncio.run(read_one())

    assert payload["mode"] == "demo"
    assert "parserAttention" not in payload
    assert "parserMeditation" not in payload


def test_run_server_calls_stream_with_mindrove_signature(monkeypatch):
    from focuscube import server

    calls = []

    class FakeWebSocketServer:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    def fake_serve(handler, host, port):
        return FakeWebSocketServer()

    async def fake_create_frame_stream(config, demo=False, require_device=False, command_queue=None):
        calls.append((config, demo, require_device))
        assert command_queue is not None
        yield demo_frame(0, config)
        raise asyncio.CancelledError()

    monkeypatch.setattr(server.websockets, "serve", fake_serve)
    monkeypatch.setattr(server, "create_frame_stream", fake_create_frame_stream)

    try:
        asyncio.run(server.run_server(FocusCubeConfig(), demo=True, require_device=False))
    except asyncio.CancelledError:
        pass

    assert len(calls) == 1
    assert calls[0][1:] == (True, False)
