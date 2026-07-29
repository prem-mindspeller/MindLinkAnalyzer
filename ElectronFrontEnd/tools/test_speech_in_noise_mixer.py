"""
Tests for speech_in_noise_mixer.py.

Run:
    cd MindLinkAnalyzer/ElectronFrontEnd/tools && python3 -m pytest test_speech_in_noise_mixer.py -v
"""
import os
import sys
import wave

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speech_in_noise_mixer import (
    AudioValidationError,
    generate_seeded_noise,
    looped_noise,
    mix_speech_in_noise,
    read_narration_wav,
    sha256_of,
    write_pcm16_wav,
)

SAMPLE_RATE = 8000  # low rate keeps the pure-Python LCG loop fast in tests


def synthetic_narration(seconds=2.0, sample_rate=SAMPLE_RATE, freq=440.0, amplitude=0.3):
    n = int(seconds * sample_rate)
    t = np.arange(n) / sample_rate
    return 0.5 * amplitude * (np.sin(2 * np.pi * freq * t) + np.sin(2 * np.pi * freq * 2.01 * t))


# ---------------------------------------------------------------------------
# Seeded noise: must exactly reproduce the runtime's LCG
# ---------------------------------------------------------------------------
class TestSeededNoise:
    def test_matches_the_javascript_lcg_by_hand(self):
        # Hand-computed from the same recurrence as OptimizedBatteryTask.jsx:
        # seed = (1664525*seed + 1013904223) mod 2^32; sample = seed/2^32*2-1.
        seed = 11011
        expected = []
        s = seed
        for _ in range(5):
            s = (1664525 * s + 1013904223) % (2 ** 32)
            expected.append((s / (2 ** 32)) * 2 - 1)
        actual = generate_seeded_noise(seed, 5)
        assert np.allclose(actual, expected)

    def test_same_seed_is_reproducible(self):
        assert np.array_equal(generate_seeded_noise(11011, 100), generate_seeded_noise(11011, 100))

    def test_different_seeds_diverge(self):
        assert not np.array_equal(generate_seeded_noise(1, 100), generate_seeded_noise(2, 100))

    def test_values_stay_within_unit_range(self):
        noise = generate_seeded_noise(11011, 5000)
        assert noise.min() >= -1.0
        assert noise.max() <= 1.0

    def test_accepts_the_raw_seed_type_the_cli_passes(self):
        # argparse type=int always gives a plain int; this just documents that
        # the function does not require pre-masking.
        assert generate_seeded_noise(11011, 3).shape == (3,)


class TestLoopedNoise:
    def test_loops_a_short_buffer_to_a_longer_duration(self):
        sample_rate = 100
        buffer_seconds = 1.0  # 100-sample base buffer
        total = looped_noise(11011, buffer_seconds, sample_rate, 250)
        base = generate_seeded_noise(11011, 100)
        assert np.array_equal(total[:100], base)
        assert np.array_equal(total[100:200], base)
        assert np.array_equal(total[200:250], base[:50])

    def test_output_length_matches_request_exactly(self):
        for total_samples in (1, 37, 4410, 44100 * 3):
            noise = looped_noise(11011, 2.0, 44100, total_samples)
            assert noise.shape == (total_samples,)


# ---------------------------------------------------------------------------
# WAV round-trip
# ---------------------------------------------------------------------------
class TestWavIO:
    def test_write_then_read_round_trips_within_pcm16_precision(self, tmp_path):
        original = 0.4 * np.sin(2 * np.pi * 220 * np.arange(4000) / SAMPLE_RATE)
        path = tmp_path / "roundtrip.wav"
        write_pcm16_wav(path, original, SAMPLE_RATE)
        recovered, sample_rate = read_narration_wav(path)
        assert sample_rate == SAMPLE_RATE
        assert np.allclose(original, recovered, atol=1 / 32767 * 2)

    def test_stereo_input_is_downmixed_to_mono(self, tmp_path):
        left = np.full(1000, 0.5)
        right = np.full(1000, -0.5)
        path = tmp_path / "stereo.wav"
        interleaved = np.empty(2000, dtype="<i2")
        interleaved[0::2] = np.round(left * 32767).astype("<i2")
        interleaved[1::2] = np.round(right * 32767).astype("<i2")
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(2)
            handle.setsampwidth(2)
            handle.setframerate(SAMPLE_RATE)
            handle.writeframes(interleaved.tobytes())
        mono, _ = read_narration_wav(path)
        assert np.allclose(mono, 0.0, atol=1e-3), "left+right average to ~0"

    def test_non_16_bit_input_is_rejected(self, tmp_path):
        path = tmp_path / "8bit.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(1)
            handle.setframerate(SAMPLE_RATE)
            handle.writeframes(bytes([128] * 100))
        with pytest.raises(AudioValidationError):
            read_narration_wav(path)

    def test_empty_wav_is_rejected(self, tmp_path):
        path = tmp_path / "empty.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(SAMPLE_RATE)
            handle.writeframes(b"")
        with pytest.raises(AudioValidationError):
            read_narration_wav(path)

    def test_output_never_clips(self, tmp_path):
        loud = np.full(2000, 5.0)  # far beyond [-1, 1]
        path = tmp_path / "loud.wav"
        write_pcm16_wav(path, loud, SAMPLE_RATE)
        recovered, _ = read_narration_wav(path)
        assert np.max(np.abs(recovered)) <= 1.0

    def test_sha256_is_deterministic_and_content_sensitive(self, tmp_path):
        a = tmp_path / "a.wav"
        b = tmp_path / "b.wav"
        write_pcm16_wav(a, synthetic_narration(), SAMPLE_RATE)
        write_pcm16_wav(b, synthetic_narration(amplitude=0.31), SAMPLE_RATE)
        assert sha256_of(a) == sha256_of(a)
        assert sha256_of(a) != sha256_of(b)


# ---------------------------------------------------------------------------
# Mixing: the actual calibration guarantee
# ---------------------------------------------------------------------------
class TestMixSpeechInNoise:
    def test_achieved_snr_matches_the_target_within_rounding(self, tmp_path):
        narration = synthetic_narration()
        for target in (0.0, 3.0, 8.0, 12.0, -3.0):
            result = mix_speech_in_noise(
                "speech_a", narration, SAMPLE_RATE, tmp_path / f"out_{target}.wav",
                target_snr_db=target,
            )
            assert abs(result.achieved_snr_db - target) < 0.02

    def test_achieved_snr_is_independently_recomputable_from_the_written_file(self, tmp_path):
        # The claim is "measured", so the number in the returned MixResult must
        # match what an independent read of the output actually contains, not
        # just the pre-write in-memory arrays.
        narration = synthetic_narration()
        output_path = tmp_path / "check.wav"
        result = mix_speech_in_noise("speech_a", narration, SAMPLE_RATE, output_path, target_snr_db=6.0)

        mixed, sample_rate = read_narration_wav(output_path)
        noise_component = looped_noise(11011, 2.0, sample_rate, mixed.size)
        # Recover the noise scale via least-squares projection of the mixed
        # signal onto the known noise waveform, then re-derive narration and
        # SNR independently of mix_speech_in_noise's internals.
        scale = np.dot(mixed, noise_component) / np.dot(noise_component, noise_component)
        recovered_noise = noise_component * scale
        recovered_narration = mixed - recovered_noise
        independent_snr = 20 * np.log10(
            np.sqrt(np.mean(recovered_narration ** 2)) / np.sqrt(np.mean(recovered_noise ** 2))
        )
        assert abs(independent_snr - result.achieved_snr_db) < 0.5

    def test_same_seed_and_target_are_bit_for_bit_reproducible(self, tmp_path):
        narration = synthetic_narration()
        r1 = mix_speech_in_noise("speech_a", narration, SAMPLE_RATE, tmp_path / "r1.wav", target_snr_db=8.0)
        r2 = mix_speech_in_noise("speech_a", narration, SAMPLE_RATE, tmp_path / "r2.wav", target_snr_db=8.0)
        assert r1.sha256 == r2.sha256

    def test_different_target_snr_changes_the_output(self, tmp_path):
        narration = synthetic_narration()
        quiet_noise = mix_speech_in_noise("speech_a", narration, SAMPLE_RATE, tmp_path / "q.wav", target_snr_db=15.0)
        loud_noise = mix_speech_in_noise("speech_a", narration, SAMPLE_RATE, tmp_path / "l.wav", target_snr_db=0.0)
        assert quiet_noise.sha256 != loud_noise.sha256
        assert quiet_noise.noise_rms < loud_noise.noise_rms

    def test_output_never_clips_even_at_low_snr(self, tmp_path):
        narration = synthetic_narration(amplitude=0.95)  # already near full scale
        result = mix_speech_in_noise(
            "speech_a", narration, SAMPLE_RATE, tmp_path / "loud.wav", target_snr_db=-6.0,
        )
        mixed, _ = read_narration_wav(result.output_path)
        assert np.max(np.abs(mixed)) <= 1.0

    def test_silent_narration_is_rejected_rather_than_mixed(self, tmp_path):
        silence = np.zeros(4000)
        with pytest.raises(AudioValidationError):
            mix_speech_in_noise("speech_a", silence, SAMPLE_RATE, tmp_path / "silent.wav")

    def test_result_records_the_correct_file_and_metadata(self, tmp_path):
        narration = synthetic_narration(seconds=3.0)
        output_path = tmp_path / "meta.wav"
        result = mix_speech_in_noise("speech_b", narration, SAMPLE_RATE, output_path, target_snr_db=5.0)
        assert result.form_id == "speech_b"
        assert result.output_path == output_path
        assert result.target_snr_db == 5.0
        assert abs(result.duration_seconds - 3.0) < 0.01
        assert result.sha256 == sha256_of(output_path)

    def test_a_different_seed_changes_the_noise_and_the_output(self, tmp_path):
        narration = synthetic_narration()
        default_seed = mix_speech_in_noise("speech_a", narration, SAMPLE_RATE, tmp_path / "s1.wav", seed=11011)
        other_seed = mix_speech_in_noise("speech_a", narration, SAMPLE_RATE, tmp_path / "s2.wav", seed=42)
        assert default_seed.sha256 != other_seed.sha256
