import asyncio

import numpy as np

from focuscube.config import FocusCubeConfig
from focuscube.features import (
    AdaptiveNormalizer,
    attention_from_normalized,
    build_payload,
    compute_band_features,
    demo_frame,
    warming_frame,
)


def sine_wave(freq, fs=256, seconds=3, amplitude=50):
    t = np.arange(0, seconds, 1 / fs)
    return amplitude * np.sin(2 * np.pi * freq * t)


def test_compute_band_features_detects_alpha_from_raw_samples():
    features = compute_band_features(sine_wave(10))

    assert features.bands["alpha"] > features.bands["beta"] * 4
    assert features.relative["alpha"] > 0.55


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
            "port": "COM7",
            "battery": 88,
            "firmwareVersion": "1.2",
            "sampleCount": 512,
        },
    )

    assert payload["device"]["port"] == "COM7"
    assert payload["device"]["battery"] == 88
    assert payload["device"]["firmwareVersion"] == "1.2"
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
        device_status={"port": "COM7", "battery": 88},
    )

    assert payload["mode"] == "device_warming"
    assert payload["sampleCount"] == 42
    assert payload["requiredSamples"] == 256
    assert payload["device"]["port"] == "COM7"
    assert payload["device"]["battery"] == 88
    assert payload["attention"] == 0.5
    assert "parserAttention" not in payload
    assert "parserMeditation" not in payload


def test_demo_stream_payload_omits_parser_attention_fields():
    from focuscube.server import create_frame_stream

    async def read_one():
        stream = create_frame_stream(FocusCubeConfig(), demo=True)
        return await anext(stream)

    payload = asyncio.run(read_one())

    assert payload["mode"] == "demo"
    assert "parserAttention" not in payload
    assert "parserMeditation" not in payload
